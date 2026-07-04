import time
import logging
from job_queue.task_queue import TaskQueue
from job_queue.job_manager import JobManager
from agents.brain_client import LocalBrainServiceClient
from agents.factory import AgentFactory
from agents.conductor import Conductor
from brain.services.brain_service import BrainService

logger = logging.getLogger("orchestra_conductor_worker")

_should_stop = False

def run_worker():
    """
    Stateless worker that blocks on dequeuing jobs, executes the Conductor,
    and handles retries, updates, and failures.
    """
    task_queue = TaskQueue()
    job_manager = JobManager()
    brain_service = BrainService()

    logger.info("Conductor worker started. Block-polling task queue 'orchestra_jobs'...")

    while not _should_stop:
        try:
            job = task_queue.dequeue_job(timeout=2)
            if not job:
                continue

            job_id = job["job_id"]
            project_id = job["project_id"]
            session_id = job["session_id"]
            product_idea = job["product_idea"]
            user_id = job.get("user_id")

            trace_id = job.get("trace_id")

            logger.info(f"Acquired job {job_id} for session {session_id}, user {user_id}, trace {trace_id}. Starting execution...")
            job_manager.update_job_status(job_id, "running")

            from brain.database import current_user_id, current_session_id, current_trace_id, current_span_id
            token = current_user_id.set(user_id or "")
            sess_token = current_session_id.set(session_id or "")
            token_trace = current_trace_id.set(trace_id or "")

            # Initialize worker tracing
            db_init = brain_service._get_db_session()
            from observability.event_logger import EventLogger
            from observability.span_manager import SpanManager
            from observability.tracer import Tracer

            event_logger = EventLogger(db_init)
            span_mgr = SpanManager(db_init)
            
            event_logger.log("JOB_STARTED", {"job_id": job_id, "session_id": session_id})
            worker_span_id = span_mgr.start_span("worker_execution", {"job_id": job_id, "session_id": session_id})
            token_span = current_span_id.set(worker_span_id)
            db_init.close()

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
                        actual_cost = billing.finalize_job_cost(
                            job_id=job_id,
                            user_id=user_id or "",
                            compute_ms=compute_ms,
                            sandbox_ms=sandbox_ms,
                            api_calls=api_calls
                        )
                        db.close()
                    except Exception as e:
                        logger.error(f"Failed to finalize cost for job {job_id}: {e}")

                    # Finalize Tracing & log complete/failed events
                    try:
                        db_finalize = brain_service._get_db_session()
                        tracer = Tracer(db_finalize)
                        span_mgr_end = SpanManager(db_finalize)
                        event_logger_end = EventLogger(db_finalize)

                        # Determine success state
                        final_sess = brain_service.get_session(session_id, user_id=user_id)
                        final_status = final_sess.get("status") if final_sess else "FAILED"
                        status_str = "success" if final_status == "COMPLETED" else "failed"

                        event_logger_end.log("JOB_COMPLETED" if status_str == "success" else "JOB_FAILED", {"final_status": final_status})
                        span_mgr_end.finish_span(worker_span_id, status=status_str)
                        
                        if trace_id:
                            tracer.end_trace(trace_id, status=status_str, duration_ms=compute_ms)

                        # Track performance metrics snapshots
                        from observability.metrics_collector import MetricsCollector
                        metrics = MetricsCollector(db_finalize)
                        metrics.record("worker_duration_ms", float(compute_ms), "ms")
                        metrics.record("sandbox_duration_ms", float(sandbox_ms), "ms")
                        metrics.record("api_calls_count", float(api_calls), "count")
                        cost_val = 0.0
                        if 'actual_cost' in locals() and hasattr(actual_cost, 'actual_cost_usd'):
                            cost_val = float(actual_cost.actual_cost_usd)
                        metrics.record("job_actual_cost", cost_val, "usd")
                        
                        db_finalize.close()
                    except Exception as trace_err:
                        logger.error(f"Failed to finalize tracing for {job_id}: {trace_err}")
            finally:
                current_user_id.reset(token)
                current_session_id.reset(sess_token)
                current_trace_id.reset(token_trace)
                current_span_id.reset(token_span)

        except Exception as loop_error:
            logger.error(f"Fatal worker exception in polling loop: {loop_error}")
            time.sleep(1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_worker()
