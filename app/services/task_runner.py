import uuid
import threading
import logging
from abc import ABC, abstractmethod
from typing import Callable, Any, Dict, Optional

logger = logging.getLogger("orchestra_task_runner")

class TaskRunner(ABC):
    """
    Abstract interface for executing long-running asynchronous tasks.
    Enables swapping background execution engines (e.g. threading, Celery, Redis Queues).
    """
    @abstractmethod
    def submit_task(self, task_id: str, func: Callable, *args, **kwargs) -> str:
        pass

    @abstractmethod
    def get_task_status(self, job_id: str) -> str:
        pass

    @abstractmethod
    def get_task_error(self, job_id: str) -> Optional[str]:
        pass

class LocalTaskRunner(TaskRunner):
    """
    Local implementation of TaskRunner using daemonized Python threads.
    """
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit_task(self, task_id: str, func: Callable, *args, **kwargs) -> str:
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        
        with self._lock:
            self._jobs[job_id] = {
                "task_id": task_id,
                "status": "queued",
                "error": None
            }
            
        def worker_wrapper():
            with self._lock:
                self._jobs[job_id]["status"] = "running"
            
            try:
                logger.info(f"TaskRunner starting job {job_id} for task {task_id}")
                func(*args, **kwargs)
                with self._lock:
                    self._jobs[job_id]["status"] = "completed"
                logger.info(f"TaskRunner completed job {job_id}")
            except Exception as e:
                logger.exception(f"TaskRunner error in job {job_id}")
                with self._lock:
                    self._jobs[job_id]["status"] = "failed"
                    self._jobs[job_id]["error"] = str(e)

        t = threading.Thread(target=worker_wrapper, name=f"worker-{job_id}")
        t.daemon = True
        t.start()
        
        return job_id

    def get_task_status(self, job_id: str) -> str:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return "unknown"
            return job["status"]

    def get_task_error(self, job_id: str) -> Optional[str]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return job["error"]


class RedisTaskRunner(TaskRunner):
    """
    Distributed queue-based task runner using Redis as the broker.
    """
    def __init__(self):
        pass

    def submit_task(self, task_id: str, func: Callable, *args, **kwargs) -> str:
        """
        Creates a job, registers state in Redis, enqueues the job, and returns the ID immediately.
        Accepts project_id, product_idea, and user_id from kwargs.
        """
        project_id = kwargs.get("project_id")
        product_idea = kwargs.get("product_idea")
        user_id = kwargs.get("user_id")
        session_id = task_id
        
        job_id = kwargs.get("job_id") or f"job-{uuid.uuid4().hex[:8]}"
        
        trace_id = kwargs.get("trace_id")
        from job_queue.task_queue import TaskQueue
        task_queue = TaskQueue()
        task_queue.enqueue_job(
            job_id=job_id,
            project_id=project_id,
            session_id=session_id,
            product_idea=product_idea,
            user_id=user_id,
            trace_id=trace_id
        )
        return job_id

    def get_task_status(self, job_id: str) -> str:
        """
        Fetches job status from Redis and maps it to task runner state.
        """
        from job_queue.job_manager import JobManager
        job_manager = JobManager()
        job = job_manager.get_job(job_id)
        if not job:
            return "unknown"
        
        status = job.get("status", "queued")
        # Map success state to completed state expected by the API layer
        if status == "success":
            return "completed"
        return status

    def get_task_error(self, job_id: str) -> Optional[str]:
        """
        Fetches error message from Redis if execution failed.
        """
        from job_queue.job_manager import JobManager
        job_manager = JobManager()
        job = job_manager.get_job(job_id)
        if not job:
            return None
        return job.get("error_message")
