from fastapi import Request, Depends, HTTPException, status
from app.dependencies.auth import get_current_user
from billing.rate_limiter import RateLimiter

rate_limiter_instance = RateLimiter()

def check_rate_limits(request: Request, current_user: dict = Depends(get_current_user)):
    """
    FastAPI dependency that enforces request limits on routes:
    - JWT auth: 60 requests/minute.
    - API Key auth: 120 requests/minute.
    """
    if "project_id" in current_user:
        limit_type = "apikey"
        identifier = current_user["project_id"]
    else:
        limit_type = "jwt"
        identifier = current_user["id"]

    is_limited, count = rate_limiter_instance.check_rate_limit(limit_type, identifier)
    if is_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max requests reached for {limit_type}."
        )

def check_ip_rate_limit(request: Request):
    """
    Fallback IP-based rate limiting (10 requests/minute) for unauthenticated or public paths.
    """
    client_ip = request.client.host if request.client else "unknown"
    is_limited, count = rate_limiter_instance.check_rate_limit("ip", client_ip)
    if is_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Max requests reached for IP."
        )
