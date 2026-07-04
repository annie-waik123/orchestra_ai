import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from brain.repository.json_repo import (
    JSONProjectRepository,
    JSONSessionRepository,
    JSONArtifactRepository,
    JSONDecisionRepository,
    JSONAuditRepository,
    JSONEvaluationRepository,
    JSONAgentRegistryRepository
)
from brain.repository.postgres_repo import (
    SQLProjectRepository,
    SQLSessionRepository,
    SQLArtifactRepository,
    SQLDecisionRepository,
    SQLAuditRepository,
    SQLEvaluationRepository,
    SQLAgentRegistryRepository,
    SQLPredictionRepository,
    SQLOptimizationRepository,
    SQLLearningRepository
)

class BrainService:
    """
    Coordinates repository tasks, implements project lifecycle logic,
    tracks artifact version numbering, logs edits to audit trails,
    and runs session transitions.
    
    Supports both production-grade PostgreSQL/SQLAlchemy and lightweight JSON local fallbacks.
    """
    def __init__(self):
        # Detect database URL configurations
        self.db_url = os.getenv("ORCHESTRA_DATABASE_URL")
        self.test_mode = os.getenv("ORCHESTRA_TEST_MODE", "false").lower() == "true"
        
        # We enable SQL repository if DATABASE_URL is configured or in test mode
        self.use_sql = bool(self.db_url) or self.test_mode
        
        if self.use_sql:
            # Bootstrap tables automatically (safe to call repeatedly)
            from brain.database import engine, Base
            import brain.models.postgres_models
            Base.metadata.create_all(bind=engine)
        else:
            # Fallback to local file JSON database repository
            self.project_repo = JSONProjectRepository()
            self.session_repo = JSONSessionRepository()
            self.artifact_repo = JSONArtifactRepository()
            self.decision_repo = JSONDecisionRepository()
            self.audit_repo = JSONAuditRepository()
            self.evaluation_repo = JSONEvaluationRepository()
            self.agent_repo = JSONAgentRegistryRepository()
            
            # Sub-repositories not implemented in JSON repo, mock dictionaries will handle
            self.prediction_repo = None
            self.optimization_repo = None
            self.learning_repo = None

    def _get_db_session(self):
        """Creates and returns a new database session instance."""
        from brain.database import SessionLocal
        return SessionLocal()

    # --- Project Actions ---
    def create_project(self, name: str, description: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLProjectRepository(db)
                project = {
                    "id": f"proj-{uuid.uuid4().hex[:8]}",
                    "user_id": user_id,
                    "name": name,
                    "description": description,
                    "status": "active"
                }
                return repo.create(project)
            finally:
                db.close()
        else:
            project = {
                "id": f"proj-{uuid.uuid4().hex[:8]}",
                "name": name,
                "description": description,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "active"
            }
            return self.project_repo.create(project)

    def get_project(self, project_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLProjectRepository(db)
                return repo.get(project_id, user_id)
            finally:
                db.close()
        else:
            return self.project_repo.get(project_id)

    def list_projects(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLProjectRepository(db)
                return repo.list_all(user_id)
            finally:
                db.close()
        else:
            return self.project_repo.list_all()

    # --- Session Actions ---
    def create_session(self, project_id: str, git_commit_hash: Optional[str] = None, dag: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLSessionRepository(db)
                session = {
                    "id": session_id,
                    "project_id": project_id,
                    "user_id": user_id,
                    "git_commit_hash": git_commit_hash,
                    "status": "IN_PROGRESS",
                    "active_node": "init_node",
                    "progress_percentage": 0.0,
                    "dag": dag or {"nodes": [], "edges": [], "history": []}
                }
                stored = repo.create(session)
                self.log_audit(session_id, "System", "CREATE_SESSION", {"git_commit": git_commit_hash}, user_id=user_id)
                return stored
            finally:
                db.close()
        else:
            session = {
                "id": session_id,
                "project_id": project_id,
                "git_commit_hash": git_commit_hash,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "active_node": "init_node",
                "status": "IN_PROGRESS",
                "dag": dag or {"nodes": [], "edges": [], "history": []}
            }
            self.session_repo.create(session)
            self.log_audit(session_id, "System", "CREATE_SESSION", {"git_commit": git_commit_hash})
            return session

    def get_session(self, session_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLSessionRepository(db)
                return repo.get(session_id, user_id)
            finally:
                db.close()
        else:
            return self.session_repo.get(session_id)

    def list_sessions(self, project_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLSessionRepository(db)
                return repo.list_by_project(project_id, user_id)
            finally:
                db.close()
        else:
            return self.session_repo.list_by_project(project_id)

    def update_session(self, session_id: str, updates: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLSessionRepository(db)
                session = repo.get(session_id, user_id)
                if not session:
                    return None

                # Observability: Capture active_node transitions (agent execution lifecycle)
                if "active_node" in updates:
                    from observability.event_logger import EventLogger
                    from observability.span_manager import SpanManager
                    from job_queue.redis_client import RedisClient

                    evt_logger = EventLogger(db)
                    span_mgr = SpanManager(db)
                    r_client = RedisClient().client

                    old_node = session.get("active_node")
                    new_node = updates["active_node"]

                    # Close previous agent span
                    if old_node and old_node != "init_node":
                        span_key = f"active_span:{session_id}"
                        try:
                            old_span_id = r_client.get(span_key)
                            if old_span_id:
                                span_mgr.finish_span(old_span_id, status="success")
                                r_client.delete(span_key)
                        except Exception:
                            pass
                        evt_logger.log("AGENT_COMPLETED", {"agent_node": old_node, "status": "success"})

                    # Start new agent span
                    if new_node and new_node != "init_node":
                        new_span_id = span_mgr.start_span(f"execute_{new_node}", {"agent_node": new_node})
                        try:
                            r_client.set(f"active_span:{session_id}", new_span_id)
                        except Exception:
                            pass
                        evt_logger.log("AGENT_STARTED", {"agent_node": new_node})

                # Close active span on session completion or failure
                if "status" in updates and updates["status"] in ["COMPLETED", "FAILED"]:
                    from observability.event_logger import EventLogger
                    from observability.span_manager import SpanManager
                    from job_queue.redis_client import RedisClient

                    evt_logger = EventLogger(db)
                    span_mgr = SpanManager(db)
                    r_client = RedisClient().client

                    curr_node = session.get("active_node")
                    if curr_node and curr_node != "init_node":
                        span_key = f"active_span:{session_id}"
                        try:
                            old_span_id = r_client.get(span_key)
                            if old_span_id:
                                status_str = "success" if updates["status"] == "COMPLETED" else "failed"
                                span_mgr.finish_span(old_span_id, status=status_str)
                                r_client.delete(span_key)
                        except Exception:
                            pass
                        evt_logger.log("AGENT_COMPLETED", {"agent_node": curr_node, "status": status_str})

                updated_session = repo.update(session_id, updates, user_id)
                
                # Log state transitions
                if "active_node" in updates:
                    self.log_audit(session_id, "Conductor", "NODE_TRANSITION", {
                        "from_node": session.get("active_node"),
                        "to_node": updates["active_node"]
                    }, user_id=user_id)
                if "status" in updates:
                    self.log_audit(session_id, "Conductor", "STATUS_CHANGE", {
                        "from_status": session.get("status"),
                        "to_status": updates["status"]
                    }, user_id=user_id)
                return updated_session
            finally:
                db.close()
        else:
            session = self.session_repo.get(session_id)
            if not session:
                return None

            updated_session = self.session_repo.update(session_id, updates)
            
            # Log if state changes
            if "active_node" in updates:
                self.log_audit(session_id, "Conductor", "NODE_TRANSITION", {
                    "from_node": session.get("active_node"),
                    "to_node": updates["active_node"]
                })
            if "status" in updates:
                self.log_audit(session_id, "Conductor", "STATUS_CHANGE", {
                    "from_status": session.get("status"),
                    "to_status": updates["status"]
                })
            return updated_session

    # --- Artifact Actions ---
    def store_artifact(self, artifact_data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
        session_id = artifact_data["session_id"]
        file_path = artifact_data["file_path"]
        
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLArtifactRepository(db)
                latest = repo.get_by_path(session_id, file_path, user_id)
                version = 1
                if latest:
                    version = latest.get("version", 1) + 1
                
                artifact = {
                    **artifact_data,
                    "id": f"art-{uuid.uuid4().hex[:8]}",
                    "user_id": user_id,
                    "version": version
                }
                stored = repo.create(artifact)
                self.log_audit(session_id, artifact_data["generated_by"], "STORE_ARTIFACT", {
                    "file_path": file_path,
                    "version": version,
                    "artifact_id": stored["id"]
                }, user_id=user_id)
                return stored
            finally:
                db.close()
        else:
            latest = self.artifact_repo.get_by_path(session_id, file_path)
            version = 1
            if latest:
                version = latest.get("version", 1) + 1

            artifact = {
                **artifact_data,
                "id": f"art-{uuid.uuid4().hex[:8]}",
                "version": version,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            stored = self.artifact_repo.create(artifact)
            self.log_audit(session_id, artifact_data["generated_by"], "STORE_ARTIFACT", {
                "file_path": file_path,
                "version": version,
                "artifact_id": stored["id"]
            })
            return stored

    def get_artifact(self, artifact_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLArtifactRepository(db)
                return repo.get(artifact_id, user_id)
            finally:
                db.close()
        else:
            return self.artifact_repo.get(artifact_id)

    def get_latest_artifact_by_path(self, session_id: str, file_path: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLArtifactRepository(db)
                return repo.get_by_path(session_id, file_path, user_id)
            finally:
                db.close()
        else:
            return self.artifact_repo.get_by_path(session_id, file_path)

    def list_session_artifacts(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLArtifactRepository(db)
                return repo.list_by_session(session_id, user_id)
            finally:
                db.close()
        else:
            return self.artifact_repo.list_by_session(session_id)

    def get_artifact_versions(self, session_id: str, file_path: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLArtifactRepository(db)
                return repo.get_versions(session_id, file_path, user_id)
            finally:
                db.close()
        else:
            return self.artifact_repo.get_versions(session_id, file_path)

    # --- Decision Actions ---
    def store_decision(self, decision_data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                # Validate session owner
                sess = SQLSessionRepository(db).get(decision_data["session_id"], user_id)
                if not sess:
                    raise ValueError("Tenant isolation violation: invalid session context.")
                repo = SQLDecisionRepository(db)
                decision = {
                    **decision_data,
                    "id": f"dec-{uuid.uuid4().hex[:8]}"
                }
                stored = repo.create(decision)
                self.log_audit(decision_data["session_id"], decision_data["agent"], "STORE_DECISION", {
                    "title": decision_data["title"],
                    "node": decision_data["node"],
                    "decision_id": stored["id"]
                }, user_id=user_id)
                return stored
            finally:
                db.close()
        else:
            decision = {
                **decision_data,
                "id": f"dec-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            stored = self.decision_repo.create(decision)
            self.log_audit(decision_data["session_id"], decision_data["agent"], "STORE_DECISION", {
                "title": decision_data["title"],
                "node": decision_data["node"],
                "decision_id": stored["id"]
            })
            return stored

    def list_session_decisions(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLDecisionRepository(db)
                return repo.list_by_session(session_id, user_id)
            finally:
                db.close()
        else:
            return self.decision_repo.list_by_session(session_id)

    # --- Evaluation Actions ---
    def store_evaluation(self, evaluation_data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                # Validate session owner
                sess = SQLSessionRepository(db).get(evaluation_data["session_id"], user_id)
                if not sess:
                    raise ValueError("Tenant isolation violation: invalid session context.")
                repo = SQLEvaluationRepository(db)
                eval_obj = {
                    **evaluation_data,
                    "id": f"eval-{uuid.uuid4().hex[:8]}"
                }
                stored = repo.create(eval_obj)
                self.log_audit(evaluation_data["session_id"], "Evaluator", "QUALITY_GATE_EVALUATION", {
                    "score": evaluation_data["composite_score"],
                    "passed": evaluation_data["passed"]
                }, user_id=user_id)
                return stored
            finally:
                db.close()
        else:
            evaluation = {
                **evaluation_data,
                "evaluated_at": datetime.now(timezone.utc).isoformat()
            }
            stored = self.evaluation_repo.create(evaluation)
            self.log_audit(evaluation_data["session_id"], "Evaluator", "QUALITY_GATE_EVALUATION", {
                "score": evaluation_data["composite_score"],
                "passed": evaluation_data["passed"]
            })
            return stored

    def get_session_evaluation(self, session_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLEvaluationRepository(db)
                return repo.get_by_session(session_id, user_id)
            finally:
                db.close()
        else:
            return self.evaluation_repo.get_by_session(session_id)

    # --- Agent Registry Actions ---
    def register_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLAgentRegistryRepository(db)
                return repo.register(agent_data)
            finally:
                db.close()
        else:
            agent = {
                **agent_data,
                "registered_at": datetime.now(timezone.utc).isoformat()
            }
            return self.agent_repo.register(agent)

    def get_registered_agent(self, name: str) -> Optional[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLAgentRegistryRepository(db)
                return repo.get(name)
            finally:
                db.close()
        else:
            return self.agent_repo.get(name)

    def list_registered_agents(self, active_only: bool = False) -> List[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLAgentRegistryRepository(db)
                if active_only:
                    return repo.list_active()
                return repo.list_all()
            finally:
                db.close()
        else:
            if active_only:
                return self.agent_repo.list_active()
            return self.agent_repo.list_all()

    # --- Audit Logger ---
    def log_audit(self, session_id: str, agent: str, action: str, details: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                # Validate session owner
                sess = SQLSessionRepository(db).get(session_id, user_id)
                if not sess:
                    raise ValueError("Tenant isolation violation: invalid session context.")
                repo = SQLAuditRepository(db)
                audit_record = {
                    "id": f"aud-{uuid.uuid4().hex[:8]}",
                    "session_id": session_id,
                    "agent": agent,
                    "action": action,
                    "details": details or {}
                }
                return repo.create(audit_record)
            finally:
                db.close()
        else:
            audit_record = {
                "id": f"aud-{uuid.uuid4().hex[:8]}",
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": agent,
                "action": action,
                "details": details or {}
            }
            return self.audit_repo.create(audit_record)

    def list_audit_trail(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLAuditRepository(db)
                return repo.list_by_session(session_id, user_id)
            finally:
                db.close()
        else:
            return self.audit_repo.list_by_session(session_id)

    # --- Predictions ---
    def store_prediction(self, prediction_data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                # Validate session owner
                sess = SQLSessionRepository(db).get(prediction_data["session_id"], user_id)
                if not sess:
                    raise ValueError("Tenant isolation violation: invalid session context.")
                repo = SQLPredictionRepository(db)
                prediction = {
                    **prediction_data,
                    "id": f"pred-{uuid.uuid4().hex[:8]}"
                }
                return repo.create(prediction)
            finally:
                db.close()
        else:
            # Fallback mock for JSON Repo compatibility
            return prediction_data

    def list_predictions(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLPredictionRepository(db)
                return repo.list_by_session(session_id, user_id)
            finally:
                db.close()
        else:
            return []

    # --- Optimizations ---
    def store_optimization(self, optimization_data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                # Validate session owner
                sess = SQLSessionRepository(db).get(optimization_data["session_id"], user_id)
                if not sess:
                    raise ValueError("Tenant isolation violation: invalid session context.")
                repo = SQLOptimizationRepository(db)
                optimization = {
                    **optimization_data,
                    "id": f"opt-{uuid.uuid4().hex[:8]}"
                }
                return repo.create(optimization)
            finally:
                db.close()
        else:
            # Fallback mock for JSON Repo compatibility
            return optimization_data

    def list_optimizations(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLOptimizationRepository(db)
                return repo.list_by_session(session_id, user_id)
            finally:
                db.close()
        else:
            return []

    # --- Learning Reports ---
    def store_learning_report(self, learning_data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                # Validate session owner
                sess = SQLSessionRepository(db).get(learning_data["session_id"], user_id)
                if not sess:
                    raise ValueError("Tenant isolation violation: invalid session context.")
                repo = SQLLearningRepository(db)
                report = {
                    **learning_data,
                    "id": f"lrn-{uuid.uuid4().hex[:8]}"
                }
                return repo.create(report)
            finally:
                db.close()
        else:
            # Fallback mock for JSON Repo compatibility
            return learning_data

    def list_learning_reports(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.use_sql:
            db = self._get_db_session()
            try:
                repo = SQLLearningRepository(db)
                return repo.list_by_session(session_id, user_id)
            finally:
                db.close()
        else:
            return []
