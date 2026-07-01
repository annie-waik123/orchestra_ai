from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List
from brain.schemas.agent_registry import AgentRegistry, AgentRegistryCreate
from brain.services.brain_service import BrainService

router = APIRouter(prefix="/agents", tags=["agents"])

def get_brain_service():
    return BrainService()

@router.post("", response_model=AgentRegistry, status_code=210)
def register_agent(agent_in: AgentRegistryCreate, service: BrainService = Depends(get_brain_service)):
    return service.register_agent(agent_in.model_dump(mode="json"))

@router.get("/{name}", response_model=AgentRegistry)
def get_registered_agent(name: str, service: BrainService = Depends(get_brain_service)):
    agent = service.get_registered_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not registered")
    return agent

@router.get("", response_model=List[AgentRegistry])
def list_registered_agents(
    active_only: bool = Query(False, description="Filter for active agents only"),
    service: BrainService = Depends(get_brain_service)
):
    return service.list_registered_agents(active_only=active_only)
