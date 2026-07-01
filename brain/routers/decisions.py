from fastapi import APIRouter, HTTPException, Depends
from typing import List
from brain.schemas.decision import Decision, DecisionCreate
from brain.services.brain_service import BrainService

router = APIRouter(prefix="/decisions", tags=["decisions"])

def get_brain_service():
    return BrainService()

@router.post("", response_model=Decision, status_code=210)
def store_decision(decision_in: DecisionCreate, service: BrainService = Depends(get_brain_service)):
    session = service.get_session(decision_in.session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Target session does not exist")
    return service.store_decision(decision_in.model_dump(mode="json"))

@router.get("/session/{session_id}", response_model=List[Decision])
def list_session_decisions(session_id: str, service: BrainService = Depends(get_brain_service)):
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return service.list_session_decisions(session_id)
