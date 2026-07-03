from app.services.task_runner import LocalTaskRunner
from app.services.project_service import ProjectService

# Singleton runner to maintain state in-memory across calls
_task_runner = LocalTaskRunner()

def get_task_runner() -> LocalTaskRunner:
    """Dependency injector providing the unified TaskRunner instance."""
    return _task_runner

def get_project_service() -> ProjectService:
    """Dependency injector providing the ProjectService instance."""
    return ProjectService(task_runner=_task_runner)
