from app.services.task_runner import RedisTaskRunner
from app.services.project_service import ProjectService

# Singleton runner to manage job queue pushes
_task_runner = RedisTaskRunner()

def get_task_runner() -> RedisTaskRunner:
    """Dependency injector providing the unified TaskRunner instance."""
    return _task_runner

def get_project_service() -> ProjectService:
    """Dependency injector providing the ProjectService instance."""
    return ProjectService(task_runner=_task_runner)
