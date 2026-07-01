from fastapi import APIRouter, HTTPException, Depends
from typing import List
from brain.schemas.audit import Audit, AuditCreate
from brain.services.brain_service import BrainService

router = APIRouter(prefix="/audit", tags=["audit"])

def get_brain_service():
    return BrainService()

@router.post("", response_model=Audit, status_code=210)
def log_audit_action(audit_in: AuditCreate, service: BrainService = Depends(get_brain_service)):
    session = service.get_session(audit_in.session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Target session does not exist")
    return service.log_audit(
        session_id=audit_in.session_id,
        agent=audit_in.agent,
        action=audit_in.action,
        details=audit_in.details
    )

@router.get("/session/{session_id}", response_model=List[Audit])
def list_session_audit_trail(session_id: str, service: BrainService = Depends(get_brain_service)):
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return service.list_audit_trail(session_id)
