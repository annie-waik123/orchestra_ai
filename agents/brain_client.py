from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class BrainServiceClient(ABC):
    """
    Abstract interface for communicating with Project Brain.
    Ensures complete decoupling of client from underlying persistence logic.
    """
    @abstractmethod
    def store_artifact(self, artifact_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def store_decision(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def log_audit_action(
        self, 
        session_id: str, 
        agent: str, 
        action: str, 
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def check_input_presence(self, session_id: str, artifact_type: str) -> bool:
        pass

    @abstractmethod
    def get_agent_manifest(self, name: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_manifest_by_capability(self, capability: str) -> Optional[Dict[str, Any]]:
        pass


class LocalBrainServiceClient(BrainServiceClient):
    """
    Local implementation of BrainServiceClient referencing local BrainService.
    Utilized when running within the same execution process.
    """
    def __init__(self, brain_service: Optional[Any] = None):
        if not brain_service:
            # Lazy import to prevent circular dependency
            from brain.services.brain_service import BrainService
            self.service = BrainService()
        else:
            self.service = brain_service

    def store_artifact(self, artifact_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.service.store_artifact(artifact_data)

    def store_decision(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.service.store_decision(decision_data)

    def log_audit_action(
        self, 
        session_id: str, 
        agent: str, 
        action: str, 
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self.service.log_audit(session_id, agent, action, details)

    def check_input_presence(self, session_id: str, artifact_type: str) -> bool:
        # Queries artifacts in this session and checks if artifact_type exists
        artifacts = self.service.list_session_artifacts(session_id)
        for a in artifacts:
            if a.get("type") == artifact_type:
                return True
        return False

    def get_agent_manifest(self, name: str) -> Optional[Dict[str, Any]]:
        return self.service.get_registered_agent(name)

    def get_manifest_by_capability(self, capability: str) -> Optional[Dict[str, Any]]:
        agents = self.service.list_registered_agents(active_only=True)
        for agent in agents:
            # In registry, specialist capabilities might be stored in the model's outputs or manifest structure
            # e.g., agent.get("outputs") or agent.get("capabilities", {}).get("produces")
            outputs = agent.get("outputs", [])
            produces = agent.get("capabilities", {}).get("produces", []) if isinstance(agent.get("capabilities"), dict) else []
            if capability in outputs or capability in produces or capability == agent.get("name"):
                return agent
        return None
