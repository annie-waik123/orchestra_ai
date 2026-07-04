import os
import shutil
import pytest
from fastapi.testclient import TestClient

# Set environment variables for testing before importing
os.environ["ORCHESTRA_TEST_MODE"] = "true"
# Use a temporary directory inside the tests directory for storage
TEST_STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_storage")
os.environ["ORCHESTRA_STORAGE_DIR"] = TEST_STORAGE_DIR

from brain.main import app
from brain.services.brain_service import BrainService
from brain.services.context_builder import ContextBuilder

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # Ensure a clean slate for storage
    from sqlalchemy.orm import close_all_sessions
    close_all_sessions()
    from brain.database import engine
    engine.dispose()
    if os.path.exists(TEST_STORAGE_DIR):
        try:
            shutil.rmtree(TEST_STORAGE_DIR)
        except PermissionError:
            import time
            time.sleep(0.5)
            shutil.rmtree(TEST_STORAGE_DIR)
    os.makedirs(TEST_STORAGE_DIR, exist_ok=True)
    yield
    # Cleanup after tests
    close_all_sessions()
    engine.dispose()
    if os.path.exists(TEST_STORAGE_DIR):
        try:
            shutil.rmtree(TEST_STORAGE_DIR)
        except PermissionError:
            import time
            time.sleep(0.5)
            shutil.rmtree(TEST_STORAGE_DIR)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "project-brain"}

def test_project_lifecycle():
    # 1. Create Project
    response = client.post("/api/v1/projects", json={
        "name": "Rental App",
        "description": "Marketplace for rentals"
    })
    assert response.status_code == 210
    project = response.json()
    assert "id" in project
    assert project["name"] == "Rental App"
    assert project["status"] == "active"

    project_id = project["id"]

    # 2. Retrieve Project
    response = client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Rental App"

    # 3. List Projects
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_agent_registration():
    response = client.post("/api/v1/agents", json={
        "name": "Database Design Agent",
        "description": "Designs databases",
        "system_prompt": "You are a DBA...",
        "inputs": ["prd_spec", "system_architecture_decisions"],
        "outputs": ["database_schema_details", "er_diagrams"],
        "skills": ["database_modeling"],
        "mcp_servers": ["filesystem"]
    })
    assert response.status_code == 210
    agent = response.json()
    assert agent["name"] == "Database Design Agent"
    assert "registered_at" in agent

    # Retrieve Registered Agent
    response = client.get("/api/v1/agents/Database%20Design%20Agent")
    assert response.status_code == 200
    assert response.json()["skills"] == ["database_modeling"]

def test_session_lifecycle_and_dag():
    # Create Project first
    service = BrainService()
    project = service.create_project("Test Project")
    project_id = project["id"]

    # Create Session with execution DAG
    dag_meta = {
        "nodes": [
            {"id": "init_node", "name": "Initialize", "agent": "Conductor", "status": "COMPLETED"},
            {"id": "planning_node", "name": "Planning", "agent": "Planning Agent", "status": "PENDING"}
        ],
        "edges": [
            {"source": "init_node", "target": "planning_node"}
        ],
        "history": []
    }

    response = client.post("/api/v1/sessions", json={
        "project_id": project_id,
        "git_commit_hash": "abcdef123",
        "dag": dag_meta
    })
    assert response.status_code == 210
    session = response.json()
    assert "id" in session
    assert session["active_node"] == "init_node"
    assert session["dag"]["nodes"][0]["status"] == "COMPLETED"

    session_id = session["id"]

    # Update Session node and status
    response = client.patch(f"/api/v1/sessions/{session_id}", json={
        "active_node": "planning_node",
        "status": "IN_PROGRESS"
    })
    assert response.status_code == 200
    assert response.json()["active_node"] == "planning_node"

def test_artifact_versions_and_dependencies():
    service = BrainService()
    project = service.create_project("Test Proj")
    session = service.create_session(project["id"])
    session_id = session["id"]

    # Store Version 1
    response = client.post("/api/v1/artifacts", json={
        "session_id": session_id,
        "file_path": "01_prd.md",
        "checksum": "hash123",
        "type": "prd",
        "generated_by": "Planning Agent",
        "depends_on": [],
        "used_by": ["System Architecture Agent"]
    })
    assert response.status_code == 210
    art1 = response.json()
    assert art1["version"] == 1

    # Store Version 2 (same path)
    response = client.post("/api/v1/artifacts", json={
        "session_id": session_id,
        "file_path": "01_prd.md",
        "checksum": "hash456",
        "type": "prd",
        "generated_by": "Planning Agent",
        "depends_on": [],
        "used_by": ["System Architecture Agent"]
    })
    assert response.status_code == 210
    art2 = response.json()
    assert art2["version"] == 2

    # Check Versions
    response = client.get(f"/api/v1/artifacts/session/{session_id}/versions?file_path=01_prd.md")
    assert response.status_code == 200
    versions = response.json()
    assert len(versions) == 2
    assert versions[0]["version"] == 1
    assert versions[1]["version"] == 2

def test_decision_and_audit():
    service = BrainService()
    project = service.create_project("Test Proj")
    session = service.create_session(project["id"])
    session_id = session["id"]

    # Store Decision
    response = client.post("/api/v1/decisions", json={
        "session_id": session_id,
        "node": "database_design_node",
        "agent": "Database Design Agent",
        "title": "Use Postgres",
        "rationale": "For ACID properties",
        "alternatives_considered": ["MySQL", "MongoDB"],
        "confidence_score": 0.9,
        "dependencies": [],
        "artifacts_produced": ["05_database_schema.sql"]
    })
    assert response.status_code == 210
    dec = response.json()
    assert dec["title"] == "Use Postgres"

    # Check Decisions list
    response = client.get(f"/api/v1/decisions/session/{session_id}")
    assert response.status_code == 200
    assert len(response.json()) == 1

    # Check Audit Logs
    response = client.get(f"/api/v1/audit/session/{session_id}")
    assert response.status_code == 200
    # Audit list should contain create_session, store_decision logs
    assert len(response.json()) >= 2

def test_quality_gate_evaluations():
    service = BrainService()
    project = service.create_project("Test Proj")
    session = service.create_session(project["id"])
    session_id = session["id"]

    response = client.post("/api/v1/evaluations", json={
        "session_id": session_id,
        "completeness": {"score": 1.0, "details": "all files exist"},
        "consistency": {"score": 0.9, "details": "minor api warning"},
        "security": {"score": 1.0, "details": "no issues"},
        "documentation_quality": {"score": 0.8, "details": "one missing label"},
        "deployability": {"score": 0.9, "details": "docker clean"},
        "composite_score": 9.1,
        "passed": True,
        "logs": ["Starting checks", "Calculated score: 9.1", "Evaluation passed"],
        "findings": []
    })
    assert response.status_code == 210
    eval_res = response.json()
    assert eval_res["composite_score"] == 9.1
    assert eval_res["passed"] is True

    # Retrieve evaluation report
    response = client.get(f"/api/v1/evaluations/session/{session_id}")
    assert response.status_code == 200
    assert response.json()["composite_score"] == 9.1

def test_context_builder():
    service = BrainService()
    project = service.create_project("Test Proj")
    session = service.create_session(project["id"])
    session_id = session["id"]

    # Register agent
    service.register_agent({
        "name": "Database Design Agent",
        "description": "Designs databases",
        "status": "active",
        "system_prompt": "DB prompt",
        "inputs": ["prd", "architecture"],
        "outputs": ["database_schema_details"],
        "skills": ["database_modeling"],
        "mcp_servers": ["filesystem"]
    })

    # Store a decision and an artifact
    service.store_decision({
        "session_id": session_id,
        "node": "planning_node",
        "agent": "Planning Agent",
        "title": "Include tools rental scope",
        "rationale": "Primary business objective",
        "confidence_score": 1.0,
        "alternatives_considered": [],
        "dependencies": [],
        "artifacts_produced": ["01_prd.md"]
    })

    service.store_artifact({
        "session_id": session_id,
        "file_path": "01_prd.md",
        "checksum": "hash123",
        "type": "prd",
        "generated_by": "Planning Agent",
        "depends_on": [],
        "used_by": []
    })

    # Build Context
    builder = ContextBuilder()
    context = builder.build_context_for_agent(session_id, "Database Design Agent")
    
    # Assert elements exist in the context
    assert "Database Design Agent" in context
    assert "Include tools rental scope" in context
    assert "01_prd.md" in context
