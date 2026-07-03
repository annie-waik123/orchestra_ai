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
