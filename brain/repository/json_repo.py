import os
from typing import List, Optional, Dict, Any
from brain.config import settings
from brain.utils.json_db import JSONDatabase
from brain.repository.base import (
    ProjectRepository,
    SessionRepository,
    ArtifactRepository,
    DecisionRepository,
    AuditRepository,
    EvaluationRepository,
    AgentRegistryRepository
)

class JSONProjectRepository(ProjectRepository):
    def __init__(self):
        file_path = os.path.join(settings.STORAGE_DIR, "projects.json")
        self.db = JSONDatabase(file_path)

    def create(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        project_id = project_data["id"]
        self.db.set(project_id, project_data)
        return project_data

    def get(self, project_id: str) -> Optional[Dict[str, Any]]:
        return self.db.get(project_id)

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self.db.read_all().values())


class JSONSessionRepository(SessionRepository):
    def __init__(self):
        file_path = os.path.join(settings.STORAGE_DIR, "sessions.json")
        self.db = JSONDatabase(file_path)

    def create(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        session_id = session_data["id"]
        self.db.set(session_id, session_data)
        return session_data

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.db.get(session_id)

    def update(self, session_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        session = self.get(session_id)
        if not session:
            return None
        session.update(updates)
        self.db.set(session_id, session)
        return session

    def list_by_project(self, project_id: str) -> List[Dict[str, Any]]:
        sessions = self.db.read_all().values()
        return [s for s in sessions if s.get("project_id") == project_id]


class JSONArtifactRepository(ArtifactRepository):
    def __init__(self):
        file_path = os.path.join(settings.STORAGE_DIR, "artifacts.json")
        self.db = JSONDatabase(file_path)

    def create(self, artifact_data: Dict[str, Any]) -> Dict[str, Any]:
        artifact_id = artifact_data["id"]
        self.db.set(artifact_id, artifact_data)
        return artifact_data

    def get(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        return self.db.get(artifact_id)

    def get_by_path(self, session_id: str, file_path: str) -> Optional[Dict[str, Any]]:
        artifacts = self.db.read_all().values()
        # Find the latest version of this file path in the session
        matching = [
            a for a in artifacts 
            if a.get("session_id") == session_id and a.get("file_path") == file_path
        ]
        if not matching:
            return None
        # Sort by version descending
        matching.sort(key=lambda x: x.get("version", 1), reverse=True)
        return matching[0]

    def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        artifacts = self.db.read_all().values()
        # Get latest versions of all artifacts in this session
        latest_map = {}
        for a in artifacts:
            if a.get("session_id") == session_id:
                path = a.get("file_path")
                curr = latest_map.get(path)
                if not curr or a.get("version", 1) > curr.get("version", 1):
                    latest_map[path] = a
        return list(latest_map.values())

    def get_versions(self, session_id: str, file_path: str) -> List[Dict[str, Any]]:
        artifacts = self.db.read_all().values()
        matching = [
            a for a in artifacts 
            if a.get("session_id") == session_id and a.get("file_path") == file_path
        ]
        matching.sort(key=lambda x: x.get("version", 1))
        return matching


class JSONDecisionRepository(DecisionRepository):
    def __init__(self):
        file_path = os.path.join(settings.STORAGE_DIR, "decisions.json")
        self.db = JSONDatabase(file_path)

    def create(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        decision_id = decision_data["id"]
        self.db.set(decision_id, decision_data)
        return decision_data

    def get(self, decision_id: str) -> Optional[Dict[str, Any]]:
        return self.db.get(decision_id)

    def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        decisions = self.db.read_all().values()
        return [d for d in decisions if d.get("session_id") == session_id]


class JSONAuditRepository(AuditRepository):
    def __init__(self):
        file_path = os.path.join(settings.STORAGE_DIR, "audit.json")
        self.db = JSONDatabase(file_path)

    def create(self, audit_data: Dict[str, Any]) -> Dict[str, Any]:
        audit_id = audit_data["id"]
        self.db.set(audit_id, audit_data)
        return audit_data

    def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        records = self.db.read_all().values()
        return [r for r in records if r.get("session_id") == session_id]


class JSONEvaluationRepository(EvaluationRepository):
    def __init__(self):
        file_path = os.path.join(settings.STORAGE_DIR, "evaluations.json")
        self.db = JSONDatabase(file_path)

    def create(self, evaluation_data: Dict[str, Any]) -> Dict[str, Any]:
        session_id = evaluation_data["session_id"]
        self.db.set(session_id, evaluation_data)
        return evaluation_data

    def get_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.db.get(session_id)


class JSONAgentRegistryRepository(AgentRegistryRepository):
    def __init__(self):
        file_path = os.path.join(settings.STORAGE_DIR, "agents.json")
        self.db = JSONDatabase(file_path)

    def register(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        name = agent_data["name"]
        self.db.set(name, agent_data)
        return agent_data

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.db.get(name)

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self.db.read_all().values())

    def list_active(self) -> List[Dict[str, Any]]:
        agents = self.db.read_all().values()
        return [a for a in agents if a.get("status") == "active"]
