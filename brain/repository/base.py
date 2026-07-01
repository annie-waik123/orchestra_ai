from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

class ProjectRepository(ABC):
    @abstractmethod
    def create(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get(self, project_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_all(self) -> List[Dict[str, Any]]:
        pass


class SessionRepository(ABC):
    @abstractmethod
    def create(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def update(self, session_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_by_project(self, project_id: str) -> List[Dict[str, Any]]:
        pass


class ArtifactRepository(ABC):
    @abstractmethod
    def create(self, artifact_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_by_path(self, session_id: str, file_path: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_versions(self, session_id: str, file_path: str) -> List[Dict[str, Any]]:
        pass


class DecisionRepository(ABC):
    @abstractmethod
    def create(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get(self, decision_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        pass


class AuditRepository(ABC):
    @abstractmethod
    def create(self, audit_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        pass


class EvaluationRepository(ABC):
    @abstractmethod
    def create(self, evaluation_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        pass


class AgentRegistryRepository(ABC):
    @abstractmethod
    def register(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get(self, name: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_all(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_active(self) -> List[Dict[str, Any]]:
        pass
