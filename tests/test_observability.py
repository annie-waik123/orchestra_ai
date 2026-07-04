import os
import json
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

# Establish test environment variables
os.environ["ORCHESTRA_TEST_MODE"] = "true"
TEST_STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_storage")
os.environ["ORCHESTRA_STORAGE_DIR"] = TEST_STORAGE_DIR
db_path = os.path.join(TEST_STORAGE_DIR, "orchestra.db").replace('\\', '/')
os.environ["ORCHESTRA_DATABASE_URL"] = f"sqlite:///{db_path}"

from app.main import app
from brain.database import engine, Base, SessionLocal, current_trace_id, current_span_id
from brain.models.postgres_models import User, Project, Trace, Span, EventLog, MetricSnapshot
from job_queue.redis_client import RedisClient
from job_queue.task_queue import TaskQueue
from observability.trace_store import TraceStore
from observability.tracer import Tracer, SpanContext
from observability.event_logger import EventLogger
from observability.metrics_collector import MetricsCollector

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_teardown_db_and_redis():
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Clear MockRedis state
    mock_redis = RedisClient().client
    mock_redis._lists.clear()
    mock_redis._hashes.clear()
    mock_redis._kv.clear()
    mock_redis._ttls.clear()
    
    # Clear ContextVars
    current_trace_id.set("")
    current_span_id.set("")
    
    yield
    Base.metadata.drop_all(bind=engine)

def test_trace_id_propagation_via_api_and_queue():
    from app.dependencies import get_project_service
    from app.services.project_service import ProjectService
    from brain.services.brain_service import BrainService
    from typing import Callable, Optional
    import uuid
    from job_queue.task_queue import TaskQueue

    class MockTaskRunner:
        def submit_task(self, task_id: str, func: Callable, *args, **kwargs) -> str:
            job_id = kwargs.get("job_id") or f"job-{uuid.uuid4().hex[:8]}"
            trace_id = kwargs.get("trace_id")
            tq = TaskQueue(queue_name="observability_test_queue")
            tq.enqueue_job(
                job_id=job_id,
                project_id=kwargs.get("project_id"),
                session_id=task_id,
                product_idea=kwargs.get("product_idea"),
                user_id=kwargs.get("user_id"),
                trace_id=trace_id
            )
            return job_id

        def get_task_status(self, job_id: str) -> str:
            return "queued"
        def get_task_error(self, job_id: str) -> Optional[str]:
            return None

    app.dependency_overrides[get_project_service] = lambda: ProjectService(
        task_runner=MockTaskRunner()
    )

    db = SessionLocal()
    # 1. Register and login user
    client.post("/api/v1/auth/register", json={"email": "obs@example.com", "password": "password"})
    token = client.post("/api/v1/auth/login", json={"email": "obs@example.com", "password": "password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    user = db.query(User).filter(User.email == "obs@example.com").first()
    proj = client.post("/api/v1/projects", headers=headers, json={"name": "Obs Proj"}).json()
    proj_id = proj["id"]

    # 2. Trigger pipeline execution run
    res = client.post(f"/api/v1/projects/{proj_id}/run", headers=headers, json={"product_idea": "observability test"})
    assert res.status_code == 200
    run_data = res.json()
    job_id = run_data["job_id"]

    # 3. Dequeue job from Redis and check payload trace_id
    task_queue = TaskQueue(queue_name="observability_test_queue")
    job = task_queue.dequeue_job(timeout=1)
    assert job is not None
    assert job["job_id"] == job_id
    assert "trace_id" in job
    trace_id = job["trace_id"]
    assert trace_id.startswith("tr-")

    # 4. Verify initial database Trace and Spans were created
    trace = db.query(Trace).filter(Trace.id == trace_id).first()
    assert trace is not None
    assert trace.user_id == user.id
    assert trace.status == "running"

    # Check root span exists
    spans = db.query(Span).filter(Span.trace_id == trace_id).all()
    assert len(spans) == 1
    assert spans[0].name == "api_run_pipeline"

    # Check JOB_ENQUEUED event log
    events = db.query(EventLog).filter(EventLog.trace_id == trace_id).all()
    assert len(events) == 1
    assert events[0].event_type == "JOB_ENQUEUED"
    db.close()


def test_parent_child_span_integrity():
    db = SessionLocal()
    tracer = Tracer(db)
    
    # Start root trace
    trace_id = tracer.start_trace(user_id="user-123", session_id="sess-123")
    
    with SpanContext(db, "root_span", {"root_meta": 1}) as root:
        assert current_span_id.get() == root.span_id
        
        with SpanContext(db, "child_span_1", {"child_meta": 2}) as child1:
            assert child1.parent_span_id == root.span_id
            assert current_span_id.get() == child1.span_id
            
            with SpanContext(db, "grandchild_span", {"gc_meta": 3}) as gc:
                assert gc.parent_span_id == child1.span_id
                assert current_span_id.get() == gc.span_id
                
        # Current span returns to root after child context exits
        assert current_span_id.get() == root.span_id

    # Verify spans from DB
    spans = db.query(Span).filter(Span.trace_id == trace_id).all()
    assert len(spans) == 3
    
    root_db = next(s for s in spans if s.name == "root_span")
    child_db = next(s for s in spans if s.name == "child_span_1")
    gc_db = next(s for s in spans if s.name == "grandchild_span")

    assert root_db.parent_span_id is None
    assert child_db.parent_span_id == root_db.id
    assert gc_db.parent_span_id == child_db.id
    db.close()


def test_sandbox_trace_capture_and_telemetry():
    db = SessionLocal()
    
    # Setup active trace context
    current_trace_id.set("tr-sandbox-test")
    db.add(Trace(id="tr-sandbox-test", user_id="user-t", session_id="sess-t", status="running"))
    db.commit()

    # Enable mock sandbox execution
    from agents.tool_manager import ToolManager
    from agents.metrics import MetricsCollector as AgentMetrics
    tool_mgr = ToolManager(allowed_mcp_servers=["sandbox"], metrics=AgentMetrics("test_agent", "sess-t", "node-t"))
    tool_mgr.open()
    
    # Execute in sandbox (fallback path will run and measure elapsed duration)
    tool_mgr.execute_in_sandbox("python -c 'print(1)'", {"main.py": "print(1)"})

    # Verify that sandbox span and event logs were captured in DB
    span = db.query(Span).filter(Span.trace_id == "tr-sandbox-test", Span.name == "sandbox_execution").first()
    assert span is not None
    assert span.status == "success"
    assert "duration_ms" in span.metadata_json

    event = db.query(EventLog).filter(EventLog.trace_id == "tr-sandbox-test", EventLog.event_type == "SANDBOX_EXECUTED").first()
    assert event is not None
    assert event.span_id == span.id
    assert event.payload_json["success"] is True
    db.close()


def test_full_trace_replay_reconstruction():
    db = SessionLocal()
    tracer = Tracer(db)
    
    trace_id = tracer.start_trace(user_id="user-rep", session_id="sess-rep")
    event_logger = EventLogger(db)
    metrics = MetricsCollector(db)

    with SpanContext(db, "stage_1") as s1:
        event_logger.log("STAGE_1_START", {"step": 1})
        metrics.record("db_query_time", 4.5, "ms")

    with SpanContext(db, "stage_2") as s2:
        event_logger.log("STAGE_2_START", {"step": 2})

    tracer.end_trace(trace_id, "success", 120)

    # Fetch replay payload
    store = TraceStore(db)
    replay = store.get_trace_replay(trace_id)

    assert replay["trace_id"] == trace_id
    assert replay["status"] == "success"
    assert replay["duration_ms"] == 120
    assert len(replay["spans"]) == 2
    assert len(replay["events"]) == 2
    assert len(replay["metrics"]) == 1

    assert replay["spans"][0]["name"] == "stage_1"
    assert replay["events"][0]["event_type"] == "STAGE_1_START"
    assert replay["metrics"][0]["metric_name"] == "db_query_time"
    db.close()


def test_trace_replay_api_endpoint():
    db = SessionLocal()
    # 1. Register, login, and create trace
    client.post("/api/v1/auth/register", json={"email": "replay@example.com", "password": "password"})
    token = client.post("/api/v1/auth/login", json={"email": "replay@example.com", "password": "password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    db.add(Trace(id="tr-endpoint-test", user_id="user-t2", session_id="sess-t2", status="running"))
    db.commit()

    # Get trace details via API
    res = client.get("/api/v1/projects/traces/tr-endpoint-test", headers=headers)
    assert res.status_code == 200
    replay = res.json()
    assert replay["trace_id"] == "tr-endpoint-test"
    db.close()
