import time
import logging
from job_queue.task_queue import TaskQueue
from job_queue.job_manager import JobManager
from agents.brain_client import LocalBrainServiceClient
from agents.factory import AgentFactory
from agents.conductor import Conductor
from brain.services.brain_service import BrainService

logger = logging.getLogger("orchestra_conductor_worker")

def run_worker():
    """
    Stateless worker that blocks on dequeuing jobs, executes the Conductor,
    and handles retries, updates, and failures.
    """
    task_queue = TaskQueue()
    job_manager = JobManager()
    brain_service = BrainService()

    logger.info("Conductor worker started. Block-polling task queue 'orchestra_jobs'...")

    while True:
        try:
            job = task_queue.dequeue_job(timeout=2)
            if not job:
                continue

            job_id = job["job_id"]
            project_id = job["project_id"]
            session_id = job["session_id"]
            product_idea = job["product_idea"]
            user_id = job.get("user_id")

            logger.info(f"Acquired job {job_id} for session {session_id} and user {user_id}. Starting execution...")
            job_manager.update_job_status(job_id, "running")

            from brain.database import current_user_id
            token = current_user_id.set(user_id or "")

            try:
                # Update session status to IN_PROGRESS in postgres database
                brain_service.update_session(session_id, {"status": "IN_PROGRESS"}, user_id=user_id)

                from app.core.logging import add_project_file_handler, remove_project_file_handler
                fh = add_project_file_handler(project_id)
                try:
                    # Initialize agent orchestrators
                    brain_client = LocalBrainServiceClient()
                    agent_factory = AgentFactory(brain_client)
                    conductor = Conductor(brain_client, agent_factory)
                    
                    logger.info(f"Starting pipeline execution for project {project_id}, session {session_id}")
                    
                    conductor.run(
                        product_idea=product_idea,
                        project_id=project_id,
                        session_id=session_id
                    )
                    
                    # Fetch final run state from Project Brain
                    final_session = brain_service.get_session(session_id, user_id=user_id)
                    session_status = final_session.get("status") if final_session else "FAILED"
                    
                    if session_status == "COMPLETED":
                        job_manager.update_job_status(job_id, "success")
                        logger.info(f"Job {job_id} successfully completed Conductor run.")
                    else:
                        err_msg = f"Conductor finished but final session status was: {session_status}"
                        job_manager.handle_job_failure(job_id, err_msg, product_idea)
                        # Sync failed status back to session registry
                        brain_service.update_session(session_id, {"status": "FAILED"}, user_id=user_id)
                except Exception as run_error:
                    logger.exception(f"Execution error on job {job_id}: {run_error}")
                    # Classify error name (e.g. TimeoutError, ConfigurationError, ValueError)
                    err_class = type(run_error).__name__
                    err_msg = f"[{err_class}] {str(run_error)}"
                    
                    # Route failure through retry manager
                    job_manager.handle_job_failure(job_id, err_msg, product_idea)
                    
                    # Sync failed status back to session registry
                    brain_service.update_session(session_id, {"status": "FAILED"}, user_id=user_id)
                finally:
                    remove_project_file_handler(fh)
            finally:
                current_user_id.reset(token)

        except Exception as loop_error:
            logger.error(f"Fatal worker exception in polling loop: {loop_error}")
            time.sleep(1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_worker()
