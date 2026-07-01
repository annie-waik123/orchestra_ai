from fastapi import APIRouter, HTTPException, Depends
from typing import List
from brain.schemas.project import Project, ProjectCreate
from brain.services.brain_service import BrainService

router = APIRouter(prefix="/projects", tags=["projects"])

def get_brain_service():
    return BrainService()

@router.post("", response_model=Project, status_code=210)
def create_project(project_in: ProjectCreate, service: BrainService = Depends(get_brain_service)):
    return service.create_project(name=project_in.name, description=project_in.description)

@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str, service: BrainService = Depends(get_brain_service)):
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.get("", response_model=List[Project])
def list_projects(service: BrainService = Depends(get_brain_service)):
    return service.list_projects()
