from fastapi import APIRouter, HTTPException, Depends
from brain.schemas.evaluation import Evaluation, EvaluationCreate
from brain.services.brain_service import BrainService

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

def get_brain_service():
    return BrainService()

@router.post("", response_model=Evaluation, status_code=210)
def store_evaluation(evaluation_in: EvaluationCreate, service: BrainService = Depends(get_brain_service)):
    session = service.get_session(evaluation_in.session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Target session does not exist")
    return service.store_evaluation(evaluation_in.model_dump(mode="json"))

@router.get("/session/{session_id}", response_model=Evaluation)
def get_session_evaluation(session_id: str, service: BrainService = Depends(get_brain_service)):
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    evaluation = service.get_session_evaluation(session_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="No evaluation found for this session")
    return evaluation
