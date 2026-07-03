import json
import time
import logging
from typing import Dict, Any, Optional
from job_queue.redis_client import RedisClient

logger = logging.getLogger("orchestra_job_manager")

class JobManager:
    """
    Manages job states, hash records, retry limits, and Dead-Letter Queue (DLQ) routing.
    Stores status logs inside the 'orchestra_job_states' Redis hash map.
    """
    def __init__(self, states_hash: str = "orchestra_job_states", dlq_list: str = "orchestra_dlq"):
        self.states_hash = states_hash
        self.dlq_list = dlq_list
        self.redis_client = RedisClient()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a job state dictionary by its ID from Redis.
        """
        client = self.redis_client.client
        raw_val = client.hget(self.states_hash, job_id)
        if raw_val:
            try:
                return json.loads(raw_val)
            except Exception as e:
                logger.error(f"Failed to deserialize job state {job_id}: {e}")
                return None
        return None

    def update_job_status(self, job_id: str, status: str, error_message: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Updates the status, error message, and update timestamp of an existing job.
        """
        client = self.redis_client.client
        job_data = self.get_job(job_id)
        if not job_data:
            logger.error(f"Job {job_id} not found in states hash. Cannot update status.")
            return None

        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        job_data["status"] = status
        job_data["updated_at"] = now_str
        if error_message is not None:
            job_data["error_message"] = error_message

        client.hset(self.states_hash, job_id, json.dumps(job_data))
        logger.info(f"Job {job_id} state updated: {status}")
        return job_data

    def handle_job_failure(self, job_id: str, error_message: str, product_idea: str) -> bool:
        """
        Fails or retries a job.
        If retry_count < 3, increments retry count, resets status to 'queued', and pushes back to active queue.
        Otherwise, marks status as 'failed' and pushes to the Dead-Letter Queue (DLQ).
        Returns True if job is retried, False if permanently failed.
        """
        client = self.redis_client.client
        job_data = self.get_job(job_id)
        if not job_data:
            logger.error(f"Job {job_id} not found. Cannot process failure.")
            return False

        retry_count = job_data.get("retry_count", 0)
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        if retry_count < 3:
            # Increment retry count, transition back to queued status
            job_data["retry_count"] = retry_count + 1
            job_data["status"] = "queued"
            job_data["updated_at"] = now_str
            job_data["error_message"] = f"Attempt {retry_count + 1} failed: {error_message}"
            client.hset(self.states_hash, job_id, json.dumps(job_data))
            
            # Push back to active execution queue
            retry_payload = {
                "job_id": job_id,
                "project_id": job_data["project_id"],
                "session_id": job_data["session_id"],
                "product_idea": product_idea
            }
            client.rpush("orchestra_jobs", json.dumps(retry_payload))
            logger.info(f"Retrying job {job_id}. Attempt {job_data['retry_count']}/3.")
            return True
        else:
            # Max retries exhausted, permanently fail and route to dead-letter queue (DLQ)
            job_data["status"] = "failed"
            job_data["updated_at"] = now_str
            job_data["error_message"] = f"Failed after 3 retries: {error_message}"
            client.hset(self.states_hash, job_id, json.dumps(job_data))
            
            # Push to DLQ list
            dlq_payload = {
                "job_id": job_id,
                "project_id": job_data["project_id"],
                "session_id": job_data["session_id"],
                "product_idea": product_idea,
                "error": error_message,
                "timestamp": now_str
            }
            client.rpush(self.dlq_list, json.dumps(dlq_payload))
            logger.error(f"Job {job_id} permanently failed. Pushed to dead-letter queue ({self.dlq_list}).")
            return False
