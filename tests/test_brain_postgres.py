import os
import pytest
from datetime import datetime

# Set environment to use file-backed SQLite database for testing
os.environ["ORCHESTRA_TEST_MODE"] = "true"
TEST_STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_storage")
os.environ["ORCHESTRA_STORAGE_DIR"] = TEST_STORAGE_DIR
db_path = os.path.join(TEST_STORAGE_DIR, "orchestra.db").replace('\\', '/')
os.environ["ORCHESTRA_DATABASE_URL"] = f"sqlite:///{db_path}"

from brain.database import engine, Base, SessionLocal
import brain.models.postgres_models
from brain.services.brain_service import BrainService
from brain.models.postgres_models import Project, Session as DB_Session, Artifact

@pytest.fixture(autouse=True)
def setup_db():
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
    
    # Bind engine and recreate tables
    Base.metadata.create_all(bind=new_engine)
    yield
    new_engine.dispose()

def test_project_crud():
    service = BrainService()
    
    # 1. Create Project
    project = service.create_project(
        name="Enterprise Order System",
        description="Scalable ordering platform"
    )
    
    assert project["id"].startswith("proj-")
    assert project["name"] == "Enterprise Order System"
    assert project["description"] == "Scalable ordering platform"
    assert project["status"] == "active"
    assert "created_at" in project
    assert "updated_at" in project

    # 2. Get Project
    fetched = service.get_project(project["id"])
    assert fetched is not None
    assert fetched["name"] == "Enterprise Order System"

    # 3. List Projects
    projects = service.list_projects()
    assert len(projects) == 1
    assert projects[0]["id"] == project["id"]

def test_session_lifecycle_and_updates():
    service = BrainService()
    
    # Create Project
    project = service.create_project(name="Lifecycle Project")
    project_id = project["id"]

    # 1. Create Session
    session = service.create_session(
        project_id=project_id,
        git_commit_hash="abc1234",
        dag={"nodes": ["node_1", "node_2"], "edges": []}
    )
    
    session_id = session["id"]
    assert session_id.startswith("sess-")
    assert session["project_id"] == project_id
    assert session["git_commit_hash"] == "abc1234"
    assert session["status"] == "IN_PROGRESS"
    assert session["active_node"] == "init_node"
    assert session["progress_percentage"] == 0.0
    assert session["dag"]["nodes"] == ["node_1", "node_2"]

    # 2. Update Session
    updated = service.update_session(session_id, {
        "active_node": "planning_node",
        "progress_percentage": 10.0,
        "status": "PLANNING"
    })
    
    assert updated["active_node"] == "planning_node"
    assert updated["progress_percentage"] == 10.0
    assert updated["status"] == "PLANNING"

    # 3. Verify Session fetch
    fetched = service.get_session(session_id)
    assert fetched["active_node"] == "planning_node"

def test_artifact_lineage_and_versioning():
    service = BrainService()
    
    project = service.create_project(name="Lineage Project")
    session = service.create_session(project_id=project["id"])
    session_id = session["id"]

    # 1. Store first version of artifact
    artifact_1 = service.store_artifact({
        "session_id": session_id,
        "artifact_type": "prd",
        "file_path": "docs/prd.md",
        "checksum": "hash1",
        "generated_by": "planning_agent",
        "depends_on": [],
        "used_by": []
    })

    assert artifact_1["id"].startswith("art-")
    assert artifact_1["version"] == 1
    assert artifact_1["checksum"] == "hash1"

    # 2. Store version 2 (should auto-increment)
    artifact_2 = service.store_artifact({
        "session_id": session_id,
        "artifact_type": "prd",
        "file_path": "docs/prd.md",
        "checksum": "hash2",
        "generated_by": "planning_agent",
        "depends_on": [],
        "used_by": []
    })

    assert artifact_2["version"] == 2
    assert artifact_2["checksum"] == "hash2"

    # 3. Fetch latest version by path
    latest = service.get_latest_artifact_by_path(session_id, "docs/prd.md")
    assert latest["version"] == 2
    assert latest["checksum"] == "hash2"

    # 4. Fetch artifact versions list
    versions = service.get_artifact_versions(session_id, "docs/prd.md")
    assert len(versions) == 2
    assert versions[0]["version"] == 1
    assert versions[1]["version"] == 2

    # 5. Store dependent artifact (lineage)
    dependent = service.store_artifact({
        "session_id": session_id,
        "artifact_type": "blueprint",
        "file_path": "docs/blueprint.md",
        "checksum": "bp_hash",
        "generated_by": "blueprint_agent",
        "depends_on": ["docs/prd.md"],
        "used_by": []
    })

    assert dependent["depends_on"] == ["docs/prd.md"]

def test_execution_logs_and_decisions():
    service = BrainService()
    
    project = service.create_project(name="Audit Project")
    session = service.create_session(project_id=project["id"])
    session_id = session["id"]

    # 1. Log audit log (execution log)
    audit = service.log_audit(
        session_id=session_id,
        agent="planning_agent",
        action="parse_prd",
        details={"status": "completed"}
    )
    
    assert audit["id"].startswith("aud-")
    assert audit["agent"] == "planning_agent"
    assert audit["action"] == "parse_prd"
    assert audit["details"] == {"status": "completed"}

    # Fetch audit logs
    logs = service.list_audit_trail(session_id)
    # List trail will contain create_session audit and parse_prd audit
    assert len(logs) >= 2
    assert any(log["action"] == "parse_prd" for log in logs)

    # 2. Store Decision
    decision = service.store_decision({
        "session_id": session_id,
        "agent": "planning_agent",
        "node": "planning_node",
        "title": "Use Microservices Architecture",
        "rationale": "High horizontal scalability requested",
        "confidence_score": 0.95,
        "alternatives_considered": ["Monolith", "Serverless"],
        "artifacts_produced": ["docs/prd.md"]
    })

    assert decision["id"].startswith("dec-")
    assert decision["title"] == "Use Microservices Architecture"
    assert decision["confidence_score"] == 0.95
    assert decision["alternatives_considered"] == ["Monolith", "Serverless"]

    # Fetch decisions list
    decisions = service.list_session_decisions(session_id)
    assert len(decisions) == 1
    assert decisions[0]["title"] == "Use Microservices Architecture"

def test_evaluation_prediction_optimization_learning():
    service = BrainService()
    
    project = service.create_project(name="AI Analytics Project")
    session = service.create_session(project_id=project["id"])
    session_id = session["id"]

    # 1. Store Evaluation
    evaluation = service.store_evaluation({
        "session_id": session_id,
        "composite_score": 0.88,
        "passed": True,
        "metrics": {"loc": 1200, "complexity": 14},
        "checks": [{"name": "flake8", "passed": True}]
    })

    assert evaluation["id"].startswith("eval-")
    assert evaluation["composite_score"] == 0.88
    assert evaluation["passed"] is True

    # Fetch Evaluation
    fetched_eval = service.get_session_evaluation(session_id)
    assert fetched_eval is not None
    assert fetched_eval["composite_score"] == 0.88

    # 2. Store Prediction
    prediction = service.store_prediction({
        "session_id": session_id,
        "target_node": "runtime_validation_node",
        "predicted_failures": ["port_conflict"],
        "confidence": 0.72
    })

    assert prediction["id"].startswith("pred-")
    assert prediction["target_node"] == "runtime_validation_node"
    assert prediction["confidence"] == 0.72

    # Fetch Predictions
    predictions = service.list_predictions(session_id)
    assert len(predictions) == 1
    assert predictions[0]["target_node"] == "runtime_validation_node"

    # 3. Store Optimization
    optimization = service.store_optimization({
        "session_id": session_id,
        "target_node": "optimization_node",
        "recommendations": ["cache_db_responses"],
        "impact_score": 0.9
    })

    assert optimization["id"].startswith("opt-")
    assert optimization["target_node"] == "optimization_node"
    assert optimization["impact_score"] == 0.9

    # Fetch Optimizations
    optimizations = service.list_optimizations(session_id)
    assert len(optimizations) == 1
    assert optimizations[0]["target_node"] == "optimization_node"

    # 4. Store Learning Report
    learning = service.store_learning_report({
        "session_id": session_id,
        "patterns_extracted": {"common_exceptions": ["ConnectionError"]},
        "recommendations": ["implement_retry_loop"]
    })

    assert learning["id"].startswith("lrn-")
    assert learning["patterns_extracted"] == {"common_exceptions": ["ConnectionError"]}

    # Fetch Learning Reports
    reports = service.list_learning_reports(session_id)
    assert len(reports) == 1
    assert reports[0]["patterns_extracted"] == {"common_exceptions": ["ConnectionError"]}

def test_relationship_integrity_cascade():
    """Verifies foreign key constraints cascade deletes correctly."""
    service = BrainService()
    
    project = service.create_project(name="Cascade Project")
    session = service.create_session(project_id=project["id"])
    session_id = session["id"]

    service.store_artifact({
        "session_id": session_id,
        "artifact_type": "prd",
        "file_path": "docs/prd.md",
        "checksum": "c1",
        "generated_by": "planning_agent"
    })

    # Assert session is registered
    assert service.get_session(session_id) is not None

    # Fetch DB session directly to execute deletion and check constraint cascades
    db = SessionLocal()
    try:
        # Delete Project directly from DB
        db_project = db.query(Project).filter(Project.id == project["id"]).first()
        db.delete(db_project)
        db.commit()
        
        # Verify Session and Artifact were deleted automatically by FK constraints
        db_session = db.query(DB_Session).filter(DB_Session.id == session_id).first()
        db_artifact = db.query(Artifact).filter(Artifact.session_id == session_id).first()
        
        assert db_session is None
        assert db_artifact is None
    finally:
        db.close()
