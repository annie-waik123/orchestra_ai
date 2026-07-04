from datetime import datetime, timezone
from sqlalchemy.orm import Session
from brain.models.postgres_models import UserUsage
from typing import Optional

class UsageTracker:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_usage(self, user_id: str) -> UserUsage:
        usage = self.db.query(UserUsage).filter(UserUsage.user_id == user_id).first()
        if not usage:
            usage = UserUsage(
                user_id=user_id,
                runs_count=0,
                compute_seconds=0,
                sandbox_seconds=0,
                tier="free",
                is_blocked=False,
                last_reset_at=datetime.now(timezone.utc)
            )
            self.db.add(usage)
            self.db.commit()
            self.db.refresh(usage)
        return usage

    def increment_runs(self, user_id: str) -> int:
        usage = self.get_or_create_usage(user_id)
        usage.runs_count += 1
        self.db.commit()
        self.db.refresh(usage)
        return usage.runs_count

    def update_usage_times(self, user_id: str, compute_seconds: int, sandbox_seconds: int):
        usage = self.get_or_create_usage(user_id)
        usage.compute_seconds += compute_seconds
        usage.sandbox_seconds += sandbox_seconds
        self.db.commit()
        self.db.refresh(usage)

    def set_user_tier(self, user_id: str, tier: str):
        if tier not in ["free", "pro", "enterprise"]:
            raise ValueError("Invalid tier. Choose 'free', 'pro', or 'enterprise'.")
        usage = self.get_or_create_usage(user_id)
        usage.tier = tier
        self.db.commit()

    def set_blocked_status(self, user_id: str, is_blocked: bool):
        usage = self.get_or_create_usage(user_id)
        usage.is_blocked = is_blocked
        self.db.commit()

    def reset_usage_if_needed(self, user_id: str):
        usage = self.get_or_create_usage(user_id)
        now = datetime.now(timezone.utc)
        last_reset = usage.last_reset_at
        if last_reset.tzinfo is None:
            last_reset = last_reset.replace(tzinfo=timezone.utc)
        if (now - last_reset).days >= 30:
            usage.runs_count = 0
            usage.compute_seconds = 0
            usage.sandbox_seconds = 0
            usage.last_reset_at = now
            self.db.commit()
