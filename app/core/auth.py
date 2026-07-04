import os
import time
import secrets
import hashlib
import jwt
import bcrypt
from typing import Optional

JWT_SECRET = os.environ.get("ORCHESTRA_JWT_SECRET", "orchestra-super-secure-jwt-key-2026")
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    """
    Hashes a plain text password using bcrypt.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain text password against a bcrypt hash.
    """
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_jwt_token(data: dict, expires_in_seconds: int = 86400) -> str:
    """
    Encodes claims data into a JWT access token.
    """
    to_encode = data.copy()
    expire = time.time() + expires_in_seconds
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

def decode_jwt_token(token: str) -> Optional[dict]:
    """
    Decodes and validates a JWT token. Returns claims dict or None.
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except Exception:
        return None

def generate_api_key() -> str:
    """
    Generates a secure cryptographically random prefix-marked API key.
    """
    return f"orai_pk_{secrets.token_hex(24)}"

def hash_api_key(api_key: str) -> str:
    """
    Hashes an API key using SHA-256 for secure database lookup.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
