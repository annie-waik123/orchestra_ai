from fastapi import APIRouter, HTTPException, Depends
from typing import List
from sqlalchemy.orm import Session

from app.schemas.project import (
    CreateProjectRequest,
    ProjectResponse,
    RunProjectRequest,
    RunProjectResponse,
    ProjectStatusResponse,
    ArtifactResponse,
    SessionResponse,
    LogResponse,
    ErrorResponse
)
from app.services.project_service import ProjectService
from app.dependencies import get_project_service
from app.dependencies.auth import get_current_user, get_db

router = APIRouter(prefix="/projects", tags=["projects"])

def verify_project_scope(project_id: str, current_user: dict):
    """
    If API Key was used for authentication, verify it matches the target project.
    """
    scoped_project_id = current_user.get("project_id")
    if scoped_project_id and scoped_project_id != project_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied. API Key scope does not match requested project."
        )

@router.get("", response_model=List[ProjectResponse], responses={500: {"model": ErrorResponse}})
def list_projects(
    service: ProjectService = Depends(get_project_service),
    current_user: dict = Depends(get_current_user)
):
    """Lists all registered software engineering projects for the current user."""
    try:
        return service.list_projects(user_id=current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {e}")

@router.post("", response_model=ProjectResponse, status_code=201, responses={400: {"model": ErrorResponse}})
def create_project(
    project_in: CreateProjectRequest,
    service: ProjectService = Depends(get_project_service),
    current_user: dict = Depends(get_current_user)
):
    """Creates a new software engineering project for the current user."""
    try:
        return service.create_project(
            name=project_in.name,
            description=project_in.description,
            user_id=current_user["id"]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create project: {e}")

@router.post("/{project_id}/run", response_model=RunProjectResponse, responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}})
def run_project_pipeline(
    project_id: str,
    run_in: RunProjectRequest,
    service: ProjectService = Depends(get_project_service),
    current_user: dict = Depends(get_current_user)
):
    """Submits a new async execution run for the project requirements."""
    verify_project_scope(project_id, current_user)
    project = service.get_project(project_id, user_id=current_user["id"])
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    try:
        return service.run_pipeline(
            project_id=project_id,
            product_idea=run_in.product_idea,
            user_id=current_user["id"]
        )
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to trigger execution pipeline: {e}")

@router.get("/{project_id}/sessions", response_model=List[SessionResponse], responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}})
def list_project_sessions(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: dict = Depends(get_current_user)
):
    """Lists all historical and active execution sessions for the project."""
    verify_project_scope(project_id, current_user)
    project = service.get_project(project_id, user_id=current_user["id"])
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    try:
        return service.list_sessions(project_id, user_id=current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve sessions: {e}")

@router.get("/{project_id}/status", response_model=ProjectStatusResponse, responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}})
def get_project_status(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: dict = Depends(get_current_user)
):
    """Checks progress percentage and stage statuses of the latest execution run."""
    verify_project_scope(project_id, current_user)
    project = service.get_project(project_id, user_id=current_user["id"])
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    try:
        return service.get_pipeline_status(project_id, user_id=current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile status details: {e}")

@router.get("/{project_id}/artifacts", response_model=List[ArtifactResponse], responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}})
def get_project_artifacts(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: dict = Depends(get_current_user)
):
    """Retrieves metadata of all artifacts generated in the latest session."""
    verify_project_scope(project_id, current_user)
    project = service.get_project(project_id, user_id=current_user["id"])
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    try:
        return service.get_project_artifacts(project_id, user_id=current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch artifacts: {e}")

@router.get("/{project_id}/logs", response_model=LogResponse, responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}})
def get_project_logs(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: dict = Depends(get_current_user)
):
    """Retrieves both structured database audit trails and file logs for the project run."""
    verify_project_scope(project_id, current_user)
    project = service.get_project(project_id, user_id=current_user["id"])
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    try:
        return service.get_project_logs(project_id, user_id=current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build log responses: {e}")

@router.post("/{project_id}/api-key", responses={404: {"model": ErrorResponse}})
def generate_project_api_key(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generates and returns a unique plain text API Key authorized for access to this project."""
    from brain.models.postgres_models import Project
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user["id"]).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    from app.core.auth import generate_api_key, hash_api_key
    raw_key = generate_api_key()
    project.api_key_hash = hash_api_key(raw_key)
    db.commit()
    return {"api_key": raw_key}
