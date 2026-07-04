from datetime import datetime, timezone
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session

from brain.models.postgres_models import JobCost
from billing.usage_tracker import UsageTracker
from billing.cost_model import estimate_pipeline_cost, calculate_run_cost
from billing.quota_manager import QuotaManager
from billing.rate_limiter import RateLimiter

class BillingService:
    def __init__(self, db: Session):
        self.db = db
        self.tracker = UsageTracker(db)
        self.quota_manager = QuotaManager(db)
        self.rate_limiter = RateLimiter()

    def check_pre_run_rules(self, user_id: str, dag: Dict[str, Any]) -> Tuple[bool, str, float]:
        """
        Validates quotas, checks for abuse/queue flooding, estimates cost,
        and returns (is_valid, reason, estimated_cost).
        """
        # Validate tier quotas
        is_quota_ok, quota_reason = self.quota_manager.verify_quota(user_id)
        if not is_quota_ok:
            return False, quota_reason, 0.0

        # Validate queue abuse (max 3 concurrent jobs)
        is_queue_ok, queue_reason = self.quota_manager.verify_queue_flooding(user_id)
        if not is_queue_ok:
            return False, queue_reason, 0.0

        # Cost estimation
        est_cost = estimate_pipeline_cost(dag)
        return True, "Pre-run controls verified.", est_cost

    def create_initial_cost_record(self, job_id: str, user_id: str, estimated_cost: float) -> JobCost:
        """
        Saves the initial cost record before enqueuing the pipeline job.
        """
        cost_record = JobCost(
            job_id=job_id,
            user_id=user_id,
            compute_time_ms=0,
            sandbox_time_ms=0,
            estimated_cost_usd=estimated_cost,
            actual_cost_usd=0.0,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(cost_record)
        self.db.commit()
        self.db.refresh(cost_record)
        return cost_record

    def finalize_job_cost(self, job_id: str, user_id: str, compute_ms: int, sandbox_ms: int, api_calls: int) -> JobCost:
        """
        Finalizes compute/sandbox run telemetry and persists actual usage costs.
        Also increments runs count and compute metrics for the user.
        """
        cost_record = self.db.query(JobCost).filter(JobCost.job_id == job_id).first()
        if not cost_record:
            # Fallback if record was missing
            cost_record = JobCost(
                job_id=job_id,
                user_id=user_id,
                estimated_cost_usd=0.0,
                created_at=datetime.now(timezone.utc)
            )
            self.db.add(cost_record)

        cost_record.compute_time_ms = compute_ms
        cost_record.sandbox_time_ms = sandbox_ms

        compute_seconds = compute_ms / 1000.0
        sandbox_seconds = sandbox_ms / 1000.0
        actual_cost = calculate_run_cost(compute_seconds, sandbox_seconds, api_calls)
        
        cost_record.actual_cost_usd = actual_cost

        # Persist usage telemetry to UserUsage
        self.tracker.increment_runs(user_id)
        self.tracker.update_usage_times(user_id, int(compute_seconds), int(sandbox_seconds))

        self.db.commit()
        self.db.refresh(cost_record)
        return cost_record
