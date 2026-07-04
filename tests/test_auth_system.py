import os
import pytest
from fastapi.testclient import TestClient

# Set environment variables for testing before importing app
os.environ["ORCHESTRA_TEST_MODE"] = "true"
TEST_STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_storage")
os.environ["ORCHESTRA_STORAGE_DIR"] = TEST_STORAGE_DIR
db_path = os.path.join(TEST_STORAGE_DIR, "orchestra.db").replace('\\', '/')
os.environ["ORCHESTRA_DATABASE_URL"] = f"sqlite:///{db_path}"

from app.main import app
from app.dependencies.auth import get_current_user
from brain.database import engine, Base, SessionLocal
from brain.models.postgres_models import User, Project, Session as DB_Session

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    # Remove overrides for auth tests to verify live dependency lookup
    app.dependency_overrides.clear()
    
    # Reset database schema cleanly
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_user_registration_and_login():
    # 1. Register User A
    reg_response = client.post("/api/v1/auth/register", json={
        "email": "user_a@example.com",
        "password": "securepasswordA1"
    })
    assert reg_response.status_code == 201
    reg_data = reg_response.json()
    assert reg_data["email"] == "user_a@example.com"
    assert "id" in reg_data
    assert "password_hash" not in reg_data

    # Registering duplicate email must fail
    dup_response = client.post("/api/v1/auth/register", json={
        "email": "user_a@example.com",
        "password": "differentpassword"
    })
    assert dup_response.status_code == 400

    # 2. Login User A
    login_response = client.post("/api/v1/auth/login", json={
        "email": "user_a@example.com",
        "password": "securepasswordA1"
    })
    assert login_response.status_code == 200
    token_data = login_response.json()
    assert token_data["token_type"] == "bearer"
    assert "access_token" in token_data

    # Login with wrong password must fail
    wrong_login = client.post("/api/v1/auth/login", json={
        "email": "user_a@example.com",
        "password": "wrongpassword"
    })
    assert wrong_login.status_code == 401


def test_tenant_isolation_jwt():
    # Register and login User A
    client.post("/api/v1/auth/register", json={"email": "user_a@example.com", "password": "passwordA"})
    token_a = client.post("/api/v1/auth/login", json={"email": "user_a@example.com", "password": "passwordA"}).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register and login User B
    client.post("/api/v1/auth/register", json={"email": "user_b@example.com", "password": "passwordB"})
    token_b = client.post("/api/v1/auth/login", json={"email": "user_b@example.com", "password": "passwordB"}).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. User A creates a project
    create_res = client.post("/api/v1/projects", headers=headers_a, json={
        "name": "User A Project",
        "description": "Private project belonging to User A"
    })
    assert create_res.status_code == 201
    proj_a = create_res.json()
    proj_a_id = proj_a["id"]

    # 2. User A can list and get their project
    list_res = client.get("/api/v1/projects", headers=headers_a)
    assert len(list_res.json()) == 1
    assert list_res.json()[0]["id"] == proj_a_id

    get_res = client.get(f"/api/v1/projects/{proj_a_id}/sessions", headers=headers_a)
    assert get_res.status_code == 200

    # 3. User B CANNOT list User A's project
    list_res_b = client.get("/api/v1/projects", headers=headers_b)
    assert len(list_res_b.json()) == 0

    # 4. User B CANNOT access User A's project directly (must return 404 or block)
    get_res_b = client.get(f"/api/v1/projects/{proj_a_id}/sessions", headers=headers_b)
    assert get_res_b.status_code == 404

    # 5. User B CANNOT trigger a run on User A's project
    run_res_b = client.post(f"/api/v1/projects/{proj_a_id}/run", headers=headers_b, json={
        "product_idea": "Build a competitor app"
    })
    assert run_res_b.status_code == 404


def test_api_key_authentication_and_scope():
    # Register and login User A
    client.post("/api/v1/auth/register", json={"email": "user_a@example.com", "password": "passwordA"})
    token_a = client.post("/api/v1/auth/login", json={"email": "user_a@example.com", "password": "passwordA"}).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 1. User A creates a project
    proj_a = client.post("/api/v1/projects", headers=headers_a, json={"name": "Project A"}).json()
    proj_a_id = proj_a["id"]

    # 2. Generate API Key for Project A
    key_res = client.post(f"/api/v1/projects/{proj_a_id}/api-key", headers=headers_a)
    assert key_res.status_code == 200
    api_key = key_res.json()["api_key"]
    assert api_key.startswith("orai_pk_")

    # 3. Access Project A using API Key
    headers_key = {"X-API-Key": api_key}
    sessions_res = client.get(f"/api/v1/projects/{proj_a_id}/sessions", headers=headers_key)
    assert sessions_res.status_code == 200

    # 4. Create another project (Project B) for User A
    proj_b = client.post("/api/v1/projects", headers=headers_a, json={"name": "Project B"}).json()
    proj_b_id = proj_b["id"]

    # 5. Accessing Project B with Project A's API Key must be blocked (scope violation)
    forbidden_res = client.get(f"/api/v1/projects/{proj_b_id}/sessions", headers=headers_key)
    assert forbidden_res.status_code == 403
    assert "scope does not match" in forbidden_res.json()["detail"]


def test_unauthorized_endpoints():
    endpoints = [
        ("GET", "/api/v1/projects"),
        ("POST", "/api/v1/projects"),
        ("POST", "/api/v1/projects/any-id/run"),
        ("GET", "/api/v1/projects/any-id/sessions"),
        ("GET", "/api/v1/projects/any-id/status"),
        ("GET", "/api/v1/projects/any-id/artifacts"),
        ("GET", "/api/v1/projects/any-id/logs"),
    ]

    for method, path in endpoints:
        if method == "GET":
            res = client.get(path)
        else:
            res = client.post(path, json={})
        
        assert res.status_code == 401
        assert "Missing or invalid authentication" in res.json()["detail"]
