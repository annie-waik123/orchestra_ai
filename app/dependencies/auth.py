from fastapi import Request, Depends, HTTPException, status
from typing import Dict, Any
from brain.database import SessionLocal
from brain.models.postgres_models import User, Project
from app.core.auth import decode_jwt_token, hash_api_key

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(request: Request, db=Depends(get_db)) -> Dict[str, Any]:
    """
    Dependency resolver verifying incoming JWT tokens or project API Keys.
    Attaches the authenticated user context (user_id and email) to the path.
    """
    # 1. Attempt JWT Bearer auth
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        claims = decode_jwt_token(token)
        if claims and "user_id" in claims:
            user_id = claims["user_id"]
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return {"id": user.id, "email": user.email}

    # 2. Attempt API Key auth
    api_key = request.headers.get("X-API-Key")
    if api_key:
        hashed_key = hash_api_key(api_key)
        project = db.query(Project).filter(Project.api_key_hash == hashed_key).first()
        if project:
            user = db.query(User).filter(User.id == project.user_id).first()
            if user:
                return {"id": user.id, "email": user.email, "project_id": project.id}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authentication credentials (JWT Bearer or X-API-Key required)."
    )
