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

            from brain.database import current_user_id, current_session_id
            token = current_user_id.set(user_id or "")
            sess_token = current_session_id.set(session_id or "")

            start_time = time.time()
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

                    # Compute execution durations and finalize cost
                    compute_ms = int((time.time() - start_time) * 1000)
                    sandbox_ms = 0
                    try:
                        from job_queue.redis_client import RedisClient
                        r_client = RedisClient().client
                        key = f"sandbox_time:{session_id}"
                        val = r_client.get(key)
                        if val:
                            sandbox_ms = int(val)
                            r_client.delete(key)
                    except Exception:
                        pass

                    api_calls = 0
                    try:
                        audit_logs = brain_service.list_audit_trail(session_id, user_id=user_id)
                        api_calls = len(audit_logs)
                    except Exception:
                        pass

                    try:
                        db = brain_service._get_db_session()
                        from billing.billing_service import BillingService
                        billing = BillingService(db)
                        billing.finalize_job_cost(
                            job_id=job_id,
                            user_id=user_id or "",
                            compute_ms=compute_ms,
                            sandbox_ms=sandbox_ms,
                            api_calls=api_calls
                        )
                        db.close()
                    except Exception as e:
                        logger.error(f"Failed to finalize cost for job {job_id}: {e}")
            finally:
                current_user_id.reset(token)
                current_session_id.reset(sess_token)

        except Exception as loop_error:
            logger.error(f"Fatal worker exception in polling loop: {loop_error}")
            time.sleep(1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_worker()
