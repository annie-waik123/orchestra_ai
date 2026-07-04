import os
import time
import shutil
import pytest
from fastapi.testclient import TestClient

# Set environment variables for testing before importing
os.environ["ORCHESTRA_TEST_MODE"] = "true"
TEST_STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_storage")
os.environ["ORCHESTRA_STORAGE_DIR"] = TEST_STORAGE_DIR

from app.main import app
from app.core.config import settings

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    import brain.database
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool
    
    db_path = os.path.join(TEST_STORAGE_DIR, "orchestra.db").replace('\\', '/')
    db_url = f"sqlite:///{db_path}"
    os.environ["ORCHESTRA_DATABASE_URL"] = db_url

    from sqlalchemy.orm import close_all_sessions
    close_all_sessions()
    new_engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        poolclass=NullPool
    )
    brain.database.engine = new_engine
    brain.database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=new_engine)
    
    new_engine.dispose()
    os.makedirs(TEST_STORAGE_DIR, exist_ok=True)
    
    # Recreate tables
    from brain.database import Base
    import brain.models.postgres_models
    from brain.models.postgres_models import User
    Base.metadata.drop_all(bind=new_engine)
    Base.metadata.create_all(bind=new_engine)

    # Seed test user
    db = sessionmaker(bind=new_engine)()
    test_user = User(id="test-user-uuid", email="test@example.com", password_hash="dummy")
    db.add(test_user)
    db.commit()
    db.close()

    # Override get_current_user dependency
    from app.dependencies.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"id": "test-user-uuid", "email": "test@example.com"}

    # Start conductor background worker thread
    import workers.conductor_worker
    workers.conductor_worker._should_stop = False
    from workers.conductor_worker import run_worker
    import threading
    worker_thread = threading.Thread(target=run_worker, daemon=True)
    worker_thread.start()
    
    # Setup clean logs directory
    test_logs_dir = os.path.join(TEST_STORAGE_DIR, "logs")
    settings.LOGS_DIR = test_logs_dir
    if os.path.exists(test_logs_dir):
        try:
            shutil.rmtree(test_logs_dir)
        except Exception:
            pass
    os.makedirs(test_logs_dir, exist_ok=True)
    
    # Pre-register agents in Brain database so capability routing works
    from brain.services.brain_service import BrainService
    from agents.brain_client import LocalBrainServiceClient
    from agents.factory import AgentFactory
    
    brain_service = BrainService()
    brain_client = LocalBrainServiceClient(brain_service)
    factory = AgentFactory(brain_client)
    
    from agents.planning import PlanningAgent
    from agents.blueprint import BlueprintAgent
    from agents.implementation import ImplementationAgent
    from agents.runtime_validation import RuntimeValidationAgent
    from agents.evaluation import EvaluationAgent
    from agents.repair import RepairAgent
    from agents.learning import LearningAgent
    from agents.predictive import PredictiveAgent
    from agents.optimization import OptimizationAgent
    
    factory.register_agent_class("Planning Agent", PlanningAgent)
    factory.register_agent_class("Blueprint Agent", BlueprintAgent)
    factory.register_agent_class("implementation_agent", ImplementationAgent)
    factory.register_agent_class("runtime_validation_agent", RuntimeValidationAgent)
    factory.register_agent_class("evaluation_agent", EvaluationAgent)
    factory.register_agent_class("repair_agent", RepairAgent)
    factory.register_agent_class("learning_agent", LearningAgent)
    factory.register_agent_class("predictive_agent", PredictiveAgent)
    factory.register_agent_class("optimization_agent", OptimizationAgent)
    
    agents_config = [
        ("Planning Agent", ["prd"]),
        ("Blueprint Agent", ["blueprint_agent"]),
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
        brain_service.register_agent(manifest_dict)
        
    yield
    
    # Cleanup after test
    import workers.conductor_worker
    workers.conductor_worker._should_stop = True
    try:
        worker_thread.join(timeout=3.0)
    except Exception:
        pass
    close_all_sessions()
    if os.path.exists(TEST_STORAGE_DIR):
        try:
            shutil.rmtree(TEST_STORAGE_DIR)
        except Exception:
            pass

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"

def test_openapi_docs():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "Orchestra AI API"
    assert "paths" in data

def test_project_crud_and_execution_lifecycle():
    # 1. Create Project
    response = client.post("/api/v1/projects", json={
        "name": "E-Commerce System",
        "description": "Enterprise grade e-commerce shopping platform"
    })
    assert response.status_code == 201
    project = response.json()
    assert "id" in project
    assert project["name"] == "E-Commerce System"
    assert project["status"] == "active"
    
    project_id = project["id"]

    # 2. List Projects
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    projects = response.json()
    assert len(projects) >= 1
    assert any(p["id"] == project_id for p in projects)

    # 3. Check Initial Status (No Run Yet)
    response = client.get(f"/api/v1/projects/{project_id}/status")
    assert response.status_code == 200
    status_data = response.json()
    assert status_data["project_id"] == project_id
    assert status_data["status"] == "PENDING"
    assert status_data["progress"] == 0.0
    assert status_data["node_states"]["planning_node"] == "Pending"

    # 4. Trigger Async Pipeline Run
    response = client.post(f"/api/v1/projects/{project_id}/run", json={
        "product_idea": "Build a scalable e-commerce store with payments and shopping cart"
    })
    assert response.status_code == 200
    run_data = response.json()
    assert run_data["project_id"] == project_id
    assert "session_id" in run_data
    assert "job_id" in run_data
    assert run_data["status"] == "queued"

    session_id = run_data["session_id"]

    # 5. Wait for execution pipeline to complete (max 3 seconds)
    completed = False
    for _ in range(30):
        time.sleep(0.1)
        response = client.get(f"/api/v1/projects/{project_id}/status")
        assert response.status_code == 200
        status_data = response.json()
        if status_data["status"] in ["COMPLETED", "FAILED"]:
            completed = True
            break
            
    assert completed, f"Pipeline execution did not finish in time. Final status: {status_data['status']}"
    assert status_data["status"] == "COMPLETED"
    assert status_data["progress"] == 100.0
    assert status_data["node_states"]["learning_node"] == "Completed"

    # 6. List Sessions
    response = client.get(f"/api/v1/projects/{project_id}/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id
    assert sessions[0]["status"] == "COMPLETED"

    # 7. Get Artifacts
    response = client.get(f"/api/v1/projects/{project_id}/artifacts")
    assert response.status_code == 200
    artifacts = response.json()
    assert len(artifacts) > 0
    # The Planning Agent should produce a 'prd' artifact
    assert any(art["type"] == "prd" for art in artifacts)

    # 8. Get Logs
    response = client.get(f"/api/v1/projects/{project_id}/logs")
    assert response.status_code == 200
    logs_data = response.json()
    assert logs_data["project_id"] == project_id
    assert logs_data["session_id"] == session_id
    # Audit log should capture session creation and artifact storage
    assert len(logs_data["audit_logs"]) > 0
    # Execution logs should contain Conductor/Framework run trace
    assert "Conductor execution started" in logs_data["execution_logs"] or "Starting pipeline execution" in logs_data["execution_logs"]

def test_error_handling_and_validation():
    # 1. Invalid Project ID status lookup
    response = client.get("/api/v1/projects/proj-invalid-id/status")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()

    # 2. Run execution on invalid Project ID
    response = client.post("/api/v1/projects/proj-invalid-id/run", json={
        "product_idea": "Fail immediately"
    })
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data

    # 3. Create project with invalid body schema
    response = client.post("/api/v1/projects", json={
        "description": "Missing required field 'name'"
    })
    assert response.status_code == 422
