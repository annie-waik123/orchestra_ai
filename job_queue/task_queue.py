import json
import time
import logging
from typing import Dict, Any, Optional
from job_queue.redis_client import RedisClient

logger = logging.getLogger("orchestra_task_queue")

class TaskQueue:
    """
    Manages job enqueuing and dequeuing on Redis lists.
    Uses 'orchestra_jobs' queue list key.
    """
    def __init__(self, queue_name: str = "orchestra_jobs"):
        self.queue_name = queue_name
        self.redis_client = RedisClient()

    def enqueue_job(self, job_id: str, project_id: str, session_id: str, product_idea: str, user_id: Optional[str] = None, trace_id: Optional[str] = None) -> bool:
        """
        Pushes a serialized job dictionary onto the task queue.
        Ensures idempotency by checking if the job ID already has a status recorded.
        """
        client = self.redis_client.client
        
        # Enforce idempotency: check if job status is already stored
        existing_job = client.hget("orchestra_job_states", job_id)
        if existing_job is not None:
            logger.warning(f"Job {job_id} already exists in states hash. Ignoring duplicate enqueue request.")
            return False

        # Register the initial status as 'queued' in status hash
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        initial_state = {
            "job_id": job_id,
            "project_id": project_id,
            "session_id": session_id,
            "user_id": user_id,
            "trace_id": trace_id,
            "status": "queued",
            "retry_count": 0,
            "created_at": now_str,
            "updated_at": now_str,
            "error_message": None
        }
        client.hset("orchestra_job_states", job_id, json.dumps(initial_state))

        # Push to active queue list
        payload = {
            "job_id": job_id,
            "project_id": project_id,
            "session_id": session_id,
            "product_idea": product_idea,
            "user_id": user_id,
            "trace_id": trace_id
        }
        client.rpush(self.queue_name, json.dumps(payload))
        logger.info(f"Enqueued job {job_id} for user {user_id} and trace {trace_id} in queue '{self.queue_name}'")
        return True

    def dequeue_job(self, timeout: int = 0) -> Optional[Dict[str, Any]]:
        """
        Blocks on dequeue list pop (blpop) and parses returned JSON string.
        """
        client = self.redis_client.client
        res = client.blpop(self.queue_name, timeout=timeout)
        if res:
            _, val = res
            try:
                return json.loads(val)
            except Exception as e:
                logger.error(f"Failed to deserialize dequeued job payload: {e}")
                return None
        return None
