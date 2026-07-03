import time
import logging
from job_queue.redis_client import RedisClient

logger = logging.getLogger("orchestra_sandbox_worker")

def run_sandbox_worker():
    """
    Stateless worker polling for isolated Docker sandbox execution requests.
    A decoupled queue extension point for offloading heavy sandbox run validations.
    """
    redis_client = RedisClient()
    logger.info("Sandbox worker started. Block-polling task queue 'orchestra_sandbox_jobs'...")

    while True:
        try:
            client = redis_client.client
            # Dequeue from sandbox jobs list
            res = client.blpop("orchestra_sandbox_jobs", timeout=5)
            if not res:
                continue

            _, val = res
            logger.info(f"Sandbox acquired task execution request: {val}")
            # Placeholder validation action
            time.sleep(0.5)
            logger.info("Sandbox execution completed.")
        except Exception as e:
            logger.error(f"Error in sandbox worker loop: {e}")
            time.sleep(1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_sandbox_worker()
