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
from brain.database import engine, Base, SessionLocal
from brain.models.postgres_models import User, Project, UserUsage, JobCost
from billing.billing_service import BillingService
from billing.cost_model import estimate_pipeline_cost, calculate_run_cost
from job_queue.redis_client import RedisClient
from job_queue.task_queue import TaskQueue

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
    
    yield
    Base.metadata.drop_all(bind=engine)

def test_rate_limiting_enforcement():
    # 1. Register and login test user
    client.post("/api/v1/auth/register", json={"email": "rl@example.com", "password": "password"})
    token = client.post("/api/v1/auth/login", json={"email": "rl@example.com", "password": "password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create project
    proj = client.post("/api/v1/projects", headers=headers, json={"name": "RL Proj"}).json()
    proj_id = proj["id"]

    # 2. Simulate spamming: JWT limit is 60 req/min
    # Let's perform 60 successful calls and the 61st must be blocked
    # To speed up, we can directly call rate_limiter or increment counter in MockRedis
    from app.dependencies.rate_limiter import rate_limiter_instance
    user = SessionLocal().query(User).filter(User.email == "rl@example.com").first()
    
    # Increment counter 60 times
    for _ in range(60):
        is_limited, count = rate_limiter_instance.check_rate_limit("jwt", user.id)
        assert not is_limited

    # 61st increment triggers rate limit
    is_limited, count = rate_limiter_instance.check_rate_limit("jwt", user.id)
    assert is_limited

    # Verify endpoint returns 429 Too Many Requests when rate limited
    res = client.post(f"/api/v1/projects/{proj_id}/run", headers=headers, json={"product_idea": "test"})
    assert res.status_code == 429
    assert "Rate limit exceeded" in res.json()["detail"]


def test_quota_limits_free_tier():
    db = SessionLocal()
    # 1. Register and login User (Free tier default)
    client.post("/api/v1/auth/register", json={"email": "free@example.com", "password": "password"})
    token = client.post("/api/v1/auth/login", json={"email": "free@example.com", "password": "password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    user = db.query(User).filter(User.email == "free@example.com").first()
    proj = client.post("/api/v1/projects", headers=headers, json={"name": "Quota Proj"}).json()
    proj_id = proj["id"]

    # 2. Simulate 3 successful runs (incrementing tracker)
    from billing.usage_tracker import UsageTracker
    tracker = UsageTracker(db)
    for _ in range(3):
        tracker.increment_runs(user.id)

    # 3. 4th execution attempt must be blocked
    res = client.post(f"/api/v1/projects/{proj_id}/run", headers=headers, json={"product_idea": "should fail"})
    assert res.status_code == 402
    assert "Quota exceeded: runs count limit reached" in res.json()["detail"]
    db.close()


def test_queue_flooding_abuse_prevention():
    db = SessionLocal()
    # 1. Register and login user
    client.post("/api/v1/auth/register", json={"email": "flood@example.com", "password": "password"})
    token = client.post("/api/v1/auth/login", json={"email": "flood@example.com", "password": "password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    user = db.query(User).filter(User.email == "flood@example.com").first()
    proj = client.post("/api/v1/projects", headers=headers, json={"name": "Flood Proj"}).json()
    proj_id = proj["id"]

    mock_redis = RedisClient().client
    for i in range(3):
        job_state = {
            "user_id": user.id,
            "status": "queued"
        }
        mock_redis.hset("orchestra_job_states", f"job-flood-{i}", json.dumps(job_state))

    # 3. Triggering a 4th run must be blocked by queue flooding check
    res = client.post(f"/api/v1/projects/{proj_id}/run", headers=headers, json={"product_idea": "flood run"})
    assert res.status_code == 429
    assert "queue flooding blocked" in res.json()["detail"]
    db.close()


def test_blocked_user_prevention():
    db = SessionLocal()
    # 1. Register and login user
    client.post("/api/v1/auth/register", json={"email": "blocked@example.com", "password": "password"})
    token = client.post("/api/v1/auth/login", json={"email": "blocked@example.com", "password": "password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    user = db.query(User).filter(User.email == "blocked@example.com").first()
    proj = client.post("/api/v1/projects", headers=headers, json={"name": "Blocked Proj"}).json()
    proj_id = proj["id"]

    # 2. Flag user as blocked
    from billing.usage_tracker import UsageTracker
    tracker = UsageTracker(db)
    tracker.set_blocked_status(user.id, is_blocked=True)

    # 3. Check execution is blocked
    res = client.post(f"/api/v1/projects/{proj_id}/run", headers=headers, json={"product_idea": "test"})
    assert res.status_code == 402
    assert "blocked" in res.json()["detail"]
    db.close()


def test_cost_model_estimations():
    # Test estimation based on node size
    dag_small = {
        "nodes": [
            {"id": "planning_node"},
            {"id": "blueprint_node"}
        ]
    }
    # Nodes: 2. Sandbox: No. API Calls: 10
    # Expected: (2 * 15 * 0.0001) + 0.0 + (10 * 0.002) = 0.003 + 0.02 = 0.023
    assert estimate_pipeline_cost(dag_small) == 0.023000

    dag_large = {
        "nodes": [
            {"id": "planning_node"},
            {"id": "validation_node"}
        ]
    }
    # Nodes: 2. Sandbox: Yes (10s). API Calls: 10
    # Expected: (2 * 15 * 0.0001) + (10 * 0.0005) + (10 * 0.002) = 0.003 + 0.005 + 0.02 = 0.028
    assert estimate_pipeline_cost(dag_large) == 0.028000

    # Test actual run cost calculation
    # Compute: 10s, Sandbox: 5s, API: 15 calls
    # Expected: (10 * 0.0001) + (5 * 0.0005) + (15 * 0.002) = 0.001 + 0.0025 + 0.03 = 0.0335
    assert calculate_run_cost(10.0, 5.0, 15) == 0.0335


def test_worker_telemetry_finalization():
    db = SessionLocal()
    # Seed user, project, initial job cost
    user = User(id="user-t1", email="t1@example.com", password_hash="dummy")
    db.add(user)
    db.commit()

    billing = BillingService(db)
    billing.create_initial_cost_record("job-t1", "user-t1", estimated_cost=0.05)

    # Invoke finalize_job_cost (simulate worker recording 50s compute, 20s sandbox, 8 api calls)
    billing.finalize_job_cost(
        job_id="job-t1",
        user_id="user-t1",
        compute_ms=50000,
        sandbox_ms=20000,
        api_calls=8
    )

    # Verify database updates
    cost = db.query(JobCost).filter(JobCost.job_id == "job-t1").first()
    assert cost.compute_time_ms == 50000
    assert cost.sandbox_time_ms == 20000
    # Expected cost: (50 * 0.0001) + (20 * 0.0005) + (8 * 0.002) = 0.005 + 0.010 + 0.016 = 0.031
    assert cost.actual_cost_usd == 0.031

    # Verify user usage telemetry
    usage = db.query(UserUsage).filter(UserUsage.user_id == "user-t1").first()
    assert usage.runs_count == 1
    assert usage.compute_seconds == 50
    assert usage.sandbox_seconds == 20
    db.close()
