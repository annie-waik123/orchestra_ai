import time
from typing import Tuple
from job_queue.redis_client import RedisClient

class RateLimiter:
    def __init__(self):
        self.redis_client = RedisClient().client

    def check_rate_limit(self, limit_type: str, identifier: str) -> Tuple[bool, int]:
        """
        Checks and increments the rate limit counter for a given identifier.
        Supports fixed-window rate limiting in Redis:
        - jwt: 60 requests per minute
        - apikey: 120 requests per minute
        - ip: 10 requests per minute
        
        Returns (is_limited, count).
        """
        if limit_type == "jwt":
            limit = 60
        elif limit_type == "apikey":
            limit = 120
        else:
            limit = 10

        current_minute = int(time.time() / 60)
        key = f"rate_limit:{limit_type}:{identifier}:{current_minute}"

        try:
            count = self.redis_client.incr(key)
            if count == 1:
                self.redis_client.expire(key, 60)

            if count > limit:
                return True, count
            return False, count
        except Exception:
            # Fail-open design to prevent Redis connection issues from blocking users in production
            return False, 0
