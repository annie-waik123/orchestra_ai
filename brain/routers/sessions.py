from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List
from brain.schemas.session import Session, SessionCreate, SessionUpdate
from brain.services.brain_service import BrainService
from brain.services.context_builder import ContextBuilder

router = APIRouter(prefix="/sessions", tags=["sessions"])

def get_brain_service():
    return BrainService()

def get_context_builder():
    return ContextBuilder()

@router.post("", response_model=Session, status_code=210)
def create_session(session_in: SessionCreate, service: BrainService = Depends(get_brain_service)):
    # Check if project exists
    project = service.get_project(session_in.project_id)
    if not project:
        raise HTTPException(status_code=400, detail="Target project does not exist")
        
    dag_dict = session_in.dag.model_dump(mode="json") if session_in.dag else None
    return service.create_session(
        project_id=session_in.project_id, 
        git_commit_hash=session_in.git_commit_hash,
        dag=dag_dict
    )

@router.get("/{session_id}", response_model=Session)
def get_session(session_id: str, service: BrainService = Depends(get_brain_service)):
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@router.patch("/{session_id}", response_model=Session)
def update_session(
    session_id: str, 
    session_update: SessionUpdate, 
    service: BrainService = Depends(get_brain_service)
):
    updates = session_update.model_dump(mode="json", exclude_unset=True)
    session = service.update_session(session_id, updates)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@router.get("/{session_id}/context", response_model=str)
def get_agent_context(
    session_id: str, 
    agent_name: str = Query(..., description="Name of the requesting agent"),
    builder: ContextBuilder = Depends(get_context_builder)
):
    # Generates a tailored markdown prompt snippet containing relevant inputs
    return builder.build_context_for_agent(session_id, agent_name)
