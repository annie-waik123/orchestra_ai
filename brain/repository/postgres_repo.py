from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from brain.repository.base import (
    ProjectRepository,
    SessionRepository,
    ArtifactRepository,
    DecisionRepository,
    AuditRepository,
    EvaluationRepository,
    AgentRegistryRepository
)
from brain.models.postgres_models import (
    Project,
    Session as DB_Session,
    Artifact,
    ExecutionLog,
    Evaluation,
    Prediction,
    Optimization,
    LearningReport,
    Decision,
    AgentRegistry
)
from brain.database import current_user_id

def resolve_user_id(user_id: Optional[str]) -> str:
    uid = user_id or current_user_id.get()
    if not uid:
        import os
        if os.environ.get("ORCHESTRA_TEST_MODE") == "true":
            return "test-user-uuid"
        raise ValueError("Tenant isolation violation: user_id context not established.")
    return uid

def model_to_dict(model_obj) -> Optional[Dict[str, Any]]:
    """Helper converting SQLAlchemy models to plain dictionaries with ISO datetime formatting."""
    if not model_obj:
        return None
    res = {}
    for column in model_obj.__table__.columns:
        val = getattr(model_obj, column.name)
        if isinstance(val, datetime):
            res[column.name] = val.isoformat()
        else:
            res[column.name] = val
            
    # Reconstruct semi-structured fields for Evaluation
    if model_obj.__class__.__name__ == "Evaluation" and isinstance(model_obj.metrics, dict):
        for k, v in model_obj.metrics.items():
            if k not in res:
                res[k] = v
                
    # Provide backward compatibility aliases for AgentRegistry
    if model_obj.__class__.__name__ == "AgentRegistry":
        res["mission"] = res.get("system_prompt")
        res["allowed_mcp_servers"] = res.get("mcp_servers", [])
                
    # Provide backward compatibility aliases
    if "artifact_type" in res:
        res["type"] = res["artifact_type"]
    return res


class SQLProjectRepository(ProjectRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        user_id = resolve_user_id(project_data.get("user_id"))
        project = Project(
            id=project_data.get("id"),
            user_id=user_id,
            api_key_hash=project_data.get("api_key_hash"),
            name=project_data["name"],
            description=project_data.get("description"),
            status=project_data.get("status", "active")
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return model_to_dict(project)

    def get(self, project_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        project = self.db.query(Project).filter(Project.id == project_id, Project.user_id == uid).first()
        return model_to_dict(project)

    def list_all(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        projects = self.db.query(Project).filter(Project.user_id == uid).all()
        return [model_to_dict(p) for p in projects]


class SQLSessionRepository(SessionRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        user_id = resolve_user_id(session_data.get("user_id"))
        session = DB_Session(
            id=session_data.get("id"),
            project_id=session_data["project_id"],
            user_id=user_id,
            status=session_data.get("status", "IN_PROGRESS"),
            active_node=session_data.get("active_node"),
            progress_percentage=session_data.get("progress_percentage", 0.0),
            dag=session_data.get("dag"),
            git_commit_hash=session_data.get("git_commit_hash")
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return model_to_dict(session)

    def get(self, session_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        session = self.db.query(DB_Session).filter(DB_Session.id == session_id, DB_Session.user_id == uid).first()
        return model_to_dict(session)

    def update(self, session_id: str, updates: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        session = self.db.query(DB_Session).filter(DB_Session.id == session_id, DB_Session.user_id == uid).first()
        if not session:
            return None
        
        for key, value in updates.items():
            if hasattr(session, key):
                setattr(session, key, value)
                
        self.db.commit()
        self.db.refresh(session)
        return model_to_dict(session)

    def list_by_project(self, project_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        sessions = self.db.query(DB_Session).filter(DB_Session.project_id == project_id, DB_Session.user_id == uid).all()
        return [model_to_dict(s) for s in sessions]


class SQLArtifactRepository(ArtifactRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, artifact_data: Dict[str, Any]) -> Dict[str, Any]:
        user_id = resolve_user_id(artifact_data.get("user_id"))
        artifact = Artifact(
            id=artifact_data.get("id"),
            session_id=artifact_data["session_id"],
            user_id=user_id,
            artifact_type=artifact_data.get("artifact_type") or artifact_data.get("type"),
            file_path=artifact_data["file_path"],
            version=artifact_data.get("version", 1),
            checksum=artifact_data["checksum"],
            generated_by=artifact_data["generated_by"],
            depends_on=artifact_data.get("depends_on", []),
            used_by=artifact_data.get("used_by", [])
        )
        self.db.add(artifact)
        self.db.commit()
        self.db.refresh(artifact)
        return model_to_dict(artifact)

    def get(self, artifact_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        artifact = self.db.query(Artifact).filter(Artifact.id == artifact_id, Artifact.user_id == uid).first()
        return model_to_dict(artifact)

    def get_by_path(self, session_id: str, file_path: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        artifact = self.db.query(Artifact).filter(
            Artifact.session_id == session_id,
            Artifact.file_path == file_path,
            Artifact.user_id == uid
        ).order_by(Artifact.version.desc()).first()
        return model_to_dict(artifact)

    def list_by_session(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        artifacts = self.db.query(Artifact).filter(Artifact.session_id == session_id, Artifact.user_id == uid).all()
        latest_map = {}
        for a in artifacts:
            path = a.file_path
            curr = latest_map.get(path)
            if not curr or a.version > curr.version:
                latest_map[path] = a
        return [model_to_dict(latest_map[p]) for p in latest_map]

    def get_versions(self, session_id: str, file_path: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        artifacts = self.db.query(Artifact).filter(
            Artifact.session_id == session_id,
            Artifact.file_path == file_path,
            Artifact.user_id == uid
        ).order_by(Artifact.version.asc()).all()
        return [model_to_dict(a) for a in artifacts]


class SQLDecisionRepository(DecisionRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        decision = Decision(
            id=decision_data.get("id"),
            session_id=decision_data["session_id"],
            agent=decision_data["agent"],
            node=decision_data["node"],
            title=decision_data["title"],
            rationale=decision_data["rationale"],
            confidence_score=decision_data.get("confidence_score", 1.0),
            alternatives_considered=decision_data.get("alternatives_considered", []),
            artifacts_produced=decision_data.get("artifacts_produced", [])
        )
        self.db.add(decision)
        self.db.commit()
        self.db.refresh(decision)
        return model_to_dict(decision)

    def get(self, decision_id: str) -> Optional[Dict[str, Any]]:
        decision = self.db.query(Decision).filter(Decision.id == decision_id).first()
        return model_to_dict(decision)

    def list_by_session(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        decisions = self.db.query(Decision).join(DB_Session).filter(
            Decision.session_id == session_id,
            DB_Session.user_id == uid
        ).all()
        return [model_to_dict(d) for d in decisions]


class SQLAuditRepository(AuditRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, audit_data: Dict[str, Any]) -> Dict[str, Any]:
        audit = ExecutionLog(
            id=audit_data.get("id"),
            session_id=audit_data["session_id"],
            agent=audit_data["agent"],
            action=audit_data["action"],
            details=audit_data.get("details", {})
        )
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(audit)
        return model_to_dict(audit)

    def list_by_session(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        audits = self.db.query(ExecutionLog).join(DB_Session).filter(
            ExecutionLog.session_id == session_id,
            DB_Session.user_id == uid
        ).all()
        return [model_to_dict(a) for a in audits]


class SQLEvaluationRepository(EvaluationRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, evaluation_data: Dict[str, Any]) -> Dict[str, Any]:
        eval_obj = Evaluation(
            id=evaluation_data.get("id"),
            session_id=evaluation_data["session_id"],
            composite_score=evaluation_data["composite_score"],
            passed=evaluation_data.get("passed", True),
            metrics=evaluation_data,
            checks=evaluation_data.get("checks", [])
        )
        self.db.add(eval_obj)
        self.db.commit()
        self.db.refresh(eval_obj)
        return model_to_dict(eval_obj)

    def get_by_session(self, session_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        evaluation = self.db.query(Evaluation).join(DB_Session).filter(
            Evaluation.session_id == session_id,
            DB_Session.user_id == uid
        ).first()
        return model_to_dict(evaluation)


class SQLAgentRegistryRepository(AgentRegistryRepository):
    def __init__(self, db: Session):
        self.db = db

    def register(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        # Perform upsert check by name
        name = agent_data["name"]
        agent = self.db.query(AgentRegistry).filter(AgentRegistry.name == name).first()
        
        if not agent:
            agent = AgentRegistry(name=name)
            self.db.add(agent)
            
        agent.description = agent_data.get("description") or f"Registry entry for {name}"
        agent.status = agent_data.get("status", "active")
        
        # Manifests might define system instructions as 'mission' or 'system_prompt'
        agent.system_prompt = agent_data.get("system_prompt") or agent_data.get("mission") or f"Instructions for {name}"
        
        agent.capabilities = agent_data.get("capabilities", {})
        agent.inputs = agent_data.get("inputs", [])
        agent.outputs = agent_data.get("outputs", [])
        agent.skills = agent_data.get("skills", [])
        
        # Manifests might define mcp servers as 'allowed_mcp_servers' or 'mcp_servers'
        agent.mcp_servers = agent_data.get("mcp_servers") or agent_data.get("allowed_mcp_servers") or []
        
        self.db.commit()
        self.db.refresh(agent)
        return model_to_dict(agent)

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        agent = self.db.query(AgentRegistry).filter(AgentRegistry.name == name).first()
        return model_to_dict(agent)

    def list_all(self) -> List[Dict[str, Any]]:
        agents = self.db.query(AgentRegistry).all()
        return [model_to_dict(a) for a in agents]

    def list_active(self) -> List[Dict[str, Any]]:
        agents = self.db.query(AgentRegistry).filter(AgentRegistry.status == "active").all()
        return [model_to_dict(a) for a in agents]


class SQLPredictionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, prediction_data: Dict[str, Any]) -> Dict[str, Any]:
        prediction = Prediction(
            id=prediction_data.get("id"),
            session_id=prediction_data["session_id"],
            target_node=prediction_data["target_node"],
            predicted_failures=prediction_data.get("predicted_failures", []),
            confidence=prediction_data["confidence"]
        )
        self.db.add(prediction)
        self.db.commit()
        self.db.refresh(prediction)
        return model_to_dict(prediction)

    def list_by_session(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        predictions = self.db.query(Prediction).join(DB_Session).filter(
            Prediction.session_id == session_id,
            DB_Session.user_id == uid
        ).all()
        return [model_to_dict(p) for p in predictions]


class SQLOptimizationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, optimization_data: Dict[str, Any]) -> Dict[str, Any]:
        optimization = Optimization(
            id=optimization_data.get("id"),
            session_id=optimization_data["session_id"],
            target_node=optimization_data["target_node"],
            recommendations=optimization_data.get("recommendations", []),
            impact_score=optimization_data["impact_score"]
        )
        self.db.add(optimization)
        self.db.commit()
        self.db.refresh(optimization)
        return model_to_dict(optimization)

    def list_by_session(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        optimizations = self.db.query(Optimization).join(DB_Session).filter(
            Optimization.session_id == session_id,
            DB_Session.user_id == uid
        ).all()
        return [model_to_dict(o) for o in optimizations]


class SQLLearningRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, learning_data: Dict[str, Any]) -> Dict[str, Any]:
        report = LearningReport(
            id=learning_data.get("id"),
            session_id=learning_data["session_id"],
            patterns_extracted=learning_data.get("patterns_extracted", {}),
            recommendations=learning_data.get("recommendations", [])
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return model_to_dict(report)

    def list_by_session(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        uid = resolve_user_id(user_id)
        reports = self.db.query(LearningReport).join(DB_Session).filter(
            LearningReport.session_id == session_id,
            DB_Session.user_id == uid
        ).all()
        return [model_to_dict(r) for r in reports]
