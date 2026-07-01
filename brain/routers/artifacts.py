from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List
from brain.schemas.artifact import Artifact, ArtifactCreate
from brain.services.brain_service import BrainService

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

def get_brain_service():
    return BrainService()

@router.post("", response_model=Artifact, status_code=210)
def store_artifact(artifact_in: ArtifactCreate, service: BrainService = Depends(get_brain_service)):
    # Check if session exists
    session = service.get_session(artifact_in.session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Target session does not exist")
        
    return service.store_artifact(artifact_in.model_dump(mode="json"))

@router.get("/{artifact_id}", response_model=Artifact)
def get_artifact(artifact_id: str, service: BrainService = Depends(get_brain_service)):
    artifact = service.get_artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact

@router.get("/session/{session_id}", response_model=List[Artifact])
def list_session_artifacts(session_id: str, service: BrainService = Depends(get_brain_service)):
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return service.list_session_artifacts(session_id)

@router.get("/session/{session_id}/versions", response_model=List[Artifact])
def get_artifact_versions(
    session_id: str, 
    file_path: str = Query(..., description="Workspace relative file path"), 
    service: BrainService = Depends(get_brain_service)
):
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return service.get_artifact_versions(session_id, file_path)
