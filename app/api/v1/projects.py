from fastapi import APIRouter, HTTPException, Depends
from typing import List

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

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("", response_model=List[ProjectResponse], responses={500: {"model": ErrorResponse}})
def list_projects(service: ProjectService = Depends(get_project_service)):
    """Lists all registered software engineering projects."""
    try:
        return service.list_projects()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {e}")

@router.post("", response_model=ProjectResponse, status_code=201, responses={400: {"model": ErrorResponse}})
def create_project(
    project_in: CreateProjectRequest,
    service: ProjectService = Depends(get_project_service)
):
    """Creates a new software engineering project."""
    try:
        return service.create_project(name=project_in.name, description=project_in.description)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create project: {e}")

@router.post("/{project_id}/run", response_model=RunProjectResponse, responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}})
def run_project_pipeline(
    project_id: str,
    run_in: RunProjectRequest,
    service: ProjectService = Depends(get_project_service)
):
    """Submits a new async execution run for the project requirements."""
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    try:
        return service.run_pipeline(project_id=project_id, product_idea=run_in.product_idea)
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to trigger execution pipeline: {e}")

@router.get("/{project_id}/sessions", response_model=List[SessionResponse], responses={404: {"model": ErrorResponse}})
def list_project_sessions(
    project_id: str,
    service: ProjectService = Depends(get_project_service)
):
    """Lists all historical and active execution sessions for the project."""
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    try:
        return service.list_sessions(project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve sessions: {e}")

@router.get("/{project_id}/status", response_model=ProjectStatusResponse, responses={404: {"model": ErrorResponse}})
def get_project_status(
    project_id: str,
    service: ProjectService = Depends(get_project_service)
):
    """Checks progress percentage and stage statuses of the latest execution run."""
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    try:
        return service.get_pipeline_status(project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compile status details: {e}")

@router.get("/{project_id}/artifacts", response_model=List[ArtifactResponse], responses={404: {"model": ErrorResponse}})
def get_project_artifacts(
    project_id: str,
    service: ProjectService = Depends(get_project_service)
):
    """Retrieves metadata of all artifacts generated in the latest session."""
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    try:
        return service.get_project_artifacts(project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch artifacts: {e}")

@router.get("/{project_id}/logs", response_model=LogResponse, responses={404: {"model": ErrorResponse}})
def get_project_logs(
    project_id: str,
    service: ProjectService = Depends(get_project_service)
):
    """Retrieves both structured database audit trails and file logs for the project run."""
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with ID '{project_id}' not found.")
        
    try:
        return service.get_project_logs(project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build log responses: {e}")
