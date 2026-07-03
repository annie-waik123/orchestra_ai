import os
import time
import pytest
import threading
import json
from typing import Generator

# Force test modes
os.environ["ORCHESTRA_TEST_MODE"] = "true"
TEST_STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_storage")
os.environ["ORCHESTRA_STORAGE_DIR"] = TEST_STORAGE_DIR
db_path = os.path.join(TEST_STORAGE_DIR, "orchestra.db").replace('\\', '/')
os.environ["ORCHESTRA_DATABASE_URL"] = f"sqlite:///{db_path}"

from brain.database import engine, Base
import brain.models.postgres_models
from brain.services.brain_service import BrainService
from job_queue.redis_client import RedisClient, MockRedis
from job_queue.task_queue import TaskQueue
from job_queue.job_manager import JobManager
from workers.conductor_worker import run_worker
from agents.factory import AgentFactory

@pytest.fixture(autouse=True)
def setup_db_and_redis():
    import brain.database
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool
    
    new_engine = create_engine(
        os.environ["ORCHESTRA_DATABASE_URL"],
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        poolclass=NullPool
    )
    brain.database.engine = new_engine
    brain.database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=new_engine)
    
    new_engine.dispose()
    os.makedirs(TEST_STORAGE_DIR, exist_ok=True)
    Base.metadata.drop_all(bind=new_engine)
    Base.metadata.create_all(bind=new_engine)
    
    # Clear MockRedis states
    MockRedis._lists.clear()
    MockRedis._hashes.clear()
    
    yield
    
    # Teardown test DB and Redis
    new_engine.dispose()
    MockRedis._lists.clear()
    MockRedis._hashes.clear()

def test_job_enqueue_and_idempotency():
    task_queue = TaskQueue()
    job_manager = JobManager()

    job_id = "test-job-123"
    assert task_queue.enqueue_job(job_id, "proj-1", "sess-1", "Product Idea") == True
    
    # Verify idempotency key: double enqueue must fail
    assert task_queue.enqueue_job(job_id, "proj-1", "sess-1", "Product Idea") == False

    # Check status inside states hash
    job = job_manager.get_job(job_id)
    assert job is not None
    assert job["status"] == "queued"
    assert job["project_id"] == "proj-1"
    assert job["session_id"] == "sess-1"

def test_job_lifecycle_transitions():
    job_manager = JobManager()
    task_queue = TaskQueue()

    job_id = "test-job-456"
    task_queue.enqueue_job(job_id, "proj-2", "sess-2", "Product Idea 2")

    # Transition to running
    job_manager.update_job_status(job_id, "running")
    job = job_manager.get_job(job_id)
    assert job["status"] == "running"

    # Transition to success
    job_manager.update_job_status(job_id, "success")
    job = job_manager.get_job(job_id)
    assert job["status"] == "success"

def test_retry_limits_and_dlq_redirection():
    task_queue = TaskQueue()
    job_manager = JobManager()

    job_id = "test-job-retry"
    task_queue.enqueue_job(job_id, "proj-3", "sess-3", "Retry Idea")

    # Fail attempt 1
    is_retrying = job_manager.handle_job_failure(job_id, "TimeoutError", "Retry Idea")
    assert is_retrying == True
    job = job_manager.get_job(job_id)
    assert job["status"] == "queued"
    assert job["retry_count"] == 1
    assert "Attempt 1" in job["error_message"]

    # Fail attempt 2
    is_retrying = job_manager.handle_job_failure(job_id, "CrashError", "Retry Idea")
    assert is_retrying == True
    job = job_manager.get_job(job_id)
    assert job["retry_count"] == 2

    # Fail attempt 3
    is_retrying = job_manager.handle_job_failure(job_id, "NetworkError", "Retry Idea")
    assert is_retrying == True
    job = job_manager.get_job(job_id)
    assert job["retry_count"] == 3

    # Fail attempt 4 (Should exhaust retries and push to DLQ)
    is_retrying = job_manager.handle_job_failure(job_id, "FinalError", "Retry Idea")
    assert is_retrying == False
    job = job_manager.get_job(job_id)
    assert job["status"] == "failed"
    assert "Failed after 3 retries" in job["error_message"]

    # Verify presence in dead-letter list
    client = RedisClient().client
    dlq_len = client.llen("orchestra_dlq")
    assert dlq_len > 0

def test_worker_processing_flow():
    service = BrainService()
    task_queue = TaskQueue()
    job_manager = JobManager()

    # Pre-register stub agents config so Conductor can run planning
    factory = AgentFactory(None)
    agents_config = [
        ("Planning Agent", ["prd"]),
        ("Blueprint Agent", ["blueprint_design"]),
        ("implementation_agent", ["implementation_agent"]),
        ("runtime_validation_agent", ["runtime_validation_agent"]),
        ("evaluation_agent", ["evaluation_agent"]),
        ("repair_agent", ["repair_agent"]),
        ("learning_agent", ["learning_agent"]),
        ("predictive_agent", ["prediction_report"]),
        ("optimization_agent", ["optimization_report"]),
    ]
    for name, caps in agents_config:
        manifest_dict = factory._create_stub_manifest_dict(name, caps)
        manifest_dict["status"] = "active"
        service.register_agent(manifest_dict)

    # Setup project and session records
    project = service.create_project("Worker Project")
    pipeline = {
        "nodes": [
            {"id": "planning_node", "name": "Planning", "agent": "Planning Agent", "status": "PENDING"}
        ],
        "edges": [],
        "history": []
    }
    session = service.create_session(project_id=project["id"], dag=pipeline)
    job_id = "test-worker-job"

    # Spin up background worker daemon thread
    worker_thread = threading.Thread(target=run_worker, daemon=True)
    worker_thread.start()

    # Enqueue job
    task_queue.enqueue_job(
        job_id=job_id,
        project_id=project["id"],
        session_id=session["id"],
        product_idea="Build worker integration tests"
    )

    # Poll status for execution completion
    completed = False
    for _ in range(50):
        time.sleep(0.1)
        job = job_manager.get_job(job_id)
        if job and job["status"] in ["success", "failed"]:
            completed = True
            break

    assert completed == True
    job = job_manager.get_job(job_id)
    assert job["status"] == "success"

def test_concurrency_and_multiple_workers():
    task_queue = TaskQueue()
    job_manager = JobManager()
    
    # Spin up multiple worker threads
    workers = []
    for i in range(2):
        t = threading.Thread(target=run_worker, daemon=True)
        t.start()
        workers.append(t)

    # Enqueue multiple jobs
    job_ids = [f"concurrent-job-{i}" for i in range(3)]
    for jid in job_ids:
        # Enqueue simple jobs that don't depend on live Conductor run (or let them fail and verify state consistency)
        task_queue.enqueue_job(jid, "proj-c", "sess-c", "Concurrent Idea")

    # Give worker loops time to consume items
    time.sleep(1.0)

    # Check status consistency in Redis hash
    for jid in job_ids:
        job = job_manager.get_job(jid)
        assert job is not None
        # Since project/session registries are missing for sess-c, jobs should have ran and updated to either running/retrying/failed state
        assert job["status"] in ["queued", "running", "failed"]
