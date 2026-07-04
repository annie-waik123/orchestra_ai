import json
from typing import Tuple
from sqlalchemy.orm import Session
from brain.models.postgres_models import UserUsage
from job_queue.redis_client import RedisClient
from billing.usage_tracker import UsageTracker

# Quotas definition
TIER_QUOTAS = {
    "free": {
        "max_runs": 3,
        "max_compute_seconds": 300,
        "max_sandbox_seconds": 60
    },
    "pro": {
        "max_runs": 20,
        "max_compute_seconds": 2000,
        "max_sandbox_seconds": 300
    },
    "enterprise": {
        "max_runs": float("inf"),
        "max_compute_seconds": float("inf"),
        "max_sandbox_seconds": float("inf")
    }
}

class QuotaManager:
    def __init__(self, db: Session):
        self.db = db
        self.tracker = UsageTracker(db)
        self.redis_client = RedisClient().client

    def verify_quota(self, user_id: str) -> Tuple[bool, str]:
        """
        Ensures a user has not exceeded their runs or compute/sandbox duration limits.
        """
        usage = self.tracker.get_or_create_usage(user_id)
        self.tracker.reset_usage_if_needed(user_id)

        if usage.is_blocked:
            return False, "Access denied: user account is blocked."

        tier = usage.tier.lower()
        quota = TIER_QUOTAS.get(tier, TIER_QUOTAS["free"])

        # Validate runs count
        if usage.runs_count >= quota["max_runs"]:
            return False, f"Quota exceeded: runs count limit reached for tier '{tier}'."

        # Validate compute duration
        if usage.compute_seconds >= quota["max_compute_seconds"]:
            return False, f"Quota exceeded: compute duration limit reached for tier '{tier}'."

        # Validate sandbox duration
        if usage.sandbox_seconds >= quota["max_sandbox_seconds"]:
            return False, f"Quota exceeded: sandbox duration limit reached for tier '{tier}'."

        return True, "Quota validation passed."

    def verify_queue_flooding(self, user_id: str) -> Tuple[bool, str]:
        """
        Prevents queue flooding abuse by enforcing a maximum of 3 concurrent active/queued jobs.
        """
        active_jobs = 0
        try:
            job_states = self.redis_client.hgetall("orchestra_job_states")
            for raw_val in job_states.values():
                job = json.loads(raw_val)
                if job.get("user_id") == user_id and job.get("status") in ["queued", "running"]:
                    active_jobs += 1
        except Exception:
            # Safe fallback if connection errors occur
            pass

        if active_jobs >= 3:
            return False, f"Abuse prevention: queue flooding blocked. Active jobs limit (3) reached."

        return True, "Queue flooding check passed."
