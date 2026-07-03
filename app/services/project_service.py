import os
import uuid
import logging
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.core.logging import add_project_file_handler, remove_project_file_handler
from app.services.task_runner import TaskRunner
from brain.services.brain_service import BrainService
from brain.repository.json_repo import JSONSessionRepository

logger = logging.getLogger("orchestra_project_service")

class ProjectService:
    """
    Coordinates project management, asynchronous Conductor runs,
    status calculations, and artifact/log querying.
    """
    def __init__(self, task_runner: TaskRunner):
        self.brain_service = BrainService()
        self.session_repo = JSONSessionRepository()
        self.task_runner = task_runner
        
        # Pipeline nodes in chronological order
        self.pipeline_stages = [
            "planning_node",
            "blueprint_node",
            "implementation_node",
            "predictive_node",
            "optimization_node",
            "validation_node",
            "evaluation_node",
            "repair_node",
            "learning_node"
        ]

    def create_project(self, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new project record in the Project Brain database."""
        return self.brain_service.create_project(name, description)

    def list_projects(self) -> List[Dict[str, Any]]:
        """Lists all registered projects."""
        return self.brain_service.list_projects()

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves project details by ID."""
        return self.brain_service.get_project(project_id)

    def list_sessions(self, project_id: str) -> List[Dict[str, Any]]:
        """Lists all sessions associated with the project."""
        return self.session_repo.list_by_project(project_id)

    def run_pipeline(self, project_id: str, product_idea: str) -> Dict[str, Any]:
        """Triggers Conductor pipeline execution asynchronously."""
        project = self.brain_service.get_project(project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' does not exist.")

        pipeline = {
            "nodes": [
                {"id": "planning_node", "name": "Planning", "agent": "Planning Agent", "status": "PENDING"},
                {"id": "blueprint_node", "name": "Blueprint", "agent": "Blueprint Agent", "status": "PENDING"},
                {"id": "implementation_node", "name": "Implementation", "agent": "implementation_agent", "status": "PENDING"},
                {"id": "predictive_node", "name": "Predictive", "agent": "predictive_agent", "status": "PENDING"},
                {"id": "optimization_node", "name": "Optimization", "agent": "optimization_agent", "status": "PENDING"},
                {"id": "validation_node", "name": "Validation", "agent": "runtime_validation_agent", "status": "PENDING"},
                {"id": "evaluation_node", "name": "Evaluation", "agent": "evaluation_agent", "status": "PENDING"},
                {"id": "repair_node", "name": "Repair", "agent": "repair_agent", "status": "PENDING"},
                {"id": "learning_node", "name": "Learning", "agent": "learning_agent", "status": "PENDING"}
            ],
            "edges": [
                {"source": "planning_node", "target": "blueprint_node"},
                {"source": "blueprint_node", "target": "implementation_node"},
                {"source": "implementation_node", "target": "predictive_node"},
                {"source": "predictive_node", "target": "optimization_node"},
                {"source": "optimization_node", "target": "validation_node"},
                {"source": "validation_node", "target": "evaluation_node"},
                {"source": "evaluation_node", "target": "repair_node"},
                {"source": "repair_node", "target": "learning_node"}
            ],
            "history": []
        }

        # Create session in DB first so status checks can find it instantly
        session = self.brain_service.create_session(project_id=project_id, dag=pipeline)
        session_id = session["id"]

        def background_job():
            # Dynamically attach log file handler
            fh = add_project_file_handler(project_id)
            try:
                # Lazy import framework classes
                from agents.brain_client import LocalBrainServiceClient
                from agents.factory import AgentFactory
                from agents.conductor import Conductor
                
                logger.info(f"Starting pipeline execution for project {project_id}, session {session_id}")
                
                brain_client = LocalBrainServiceClient()
                agent_factory = AgentFactory(brain_client)
                conductor = Conductor(brain_client, agent_factory)
                
                conductor.run(
                    product_idea=product_idea,
                    project_id=project_id,
                    session_id=session_id
                )
            except Exception as e:
                logger.exception(f"Conductor execution failed for session {session_id}: {e}")
                raise e
            finally:
                remove_project_file_handler(fh)

        # Submit task to runner
        job_id = self.task_runner.submit_task(
            task_id=session_id,
            func=background_job
        )

        return {
            "project_id": project_id,
            "session_id": session_id,
            "job_id": job_id,
            "status": "queued"
        }

    def get_pipeline_status(self, project_id: str) -> Dict[str, Any]:
        """Retrieves pipeline stages, statuses, and progress percentage for the latest run."""
        sessions = self.list_sessions(project_id)
        if not sessions:
            return {
                "project_id": project_id,
                "session_id": None,
                "status": "PENDING",
                "active_stage": None,
                "progress": 0.0,
                "node_states": {stage: "Pending" for stage in self.pipeline_stages}
            }

        # Sort sessions by created_at descending or simply by name/ID to find the latest
        # (Assuming latest is the last one in list)
        sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        latest_session = sessions[0]
        session_id = latest_session["id"]
        
        # Check job runner status if failed
        session_status = latest_session.get("status", "IN_PROGRESS")
        active_node = latest_session.get("active_node", "planning_node")
        
        # Compute node states and progress
        node_states = {}
        completed_count = 0
        
        if session_status == "COMPLETED":
            for stage in self.pipeline_stages:
                node_states[stage] = "Completed"
            completed_count = len(self.pipeline_stages)
            progress = 100.0
            active_stage = None
        else:
            # Determine index of active node
            active_idx = 0
            if active_node in self.pipeline_stages:
                active_idx = self.pipeline_stages.index(active_node)
            else:
                active_idx = 0
                
            for idx, stage in enumerate(self.pipeline_stages):
                if idx < active_idx:
                    node_states[stage] = "Completed"
                    completed_count += 1
                elif idx == active_idx:
                    if session_status == "FAILED":
                        node_states[stage] = "Failed"
                    else:
                        node_states[stage] = "Executing"
                    active_stage = stage
                else:
                    node_states[stage] = "Pending"
            
            progress = (completed_count / len(self.pipeline_stages)) * 100.0
            active_stage = active_node if session_status != "FAILED" else None

        return {
            "project_id": project_id,
            "session_id": session_id,
            "status": session_status,
            "active_stage": active_stage,
            "progress": round(progress, 1),
            "node_states": node_states
        }

    def get_project_artifacts(self, project_id: str) -> List[Dict[str, Any]]:
        """Retrieves all generated artifacts from the latest project session."""
        sessions = self.list_sessions(project_id)
        if not sessions:
            return []
            
        sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        latest_session_id = sessions[0]["id"]
        
        return self.brain_service.list_session_artifacts(latest_session_id)

    def get_project_logs(self, project_id: str) -> Dict[str, Any]:
        """Retrieves structured Project Brain audit trails and execution log trace dumps."""
        sessions = self.list_sessions(project_id)
        session_id = None
        audit_logs = []
        
        if sessions:
            sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            session_id = sessions[0]["id"]
            audit_logs = self.brain_service.list_audit_trail(session_id)

        # Read execution run.log if it exists
        log_file = os.path.join(settings.LOGS_DIR, project_id, "run.log")
        execution_logs = ""
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    execution_logs = f.read()
            except Exception as e:
                execution_logs = f"Error reading log file: {e}"
        else:
            execution_logs = "No execution logs recorded yet."

        return {
            "project_id": project_id,
            "session_id": session_id,
            "audit_logs": audit_logs,
            "execution_logs": execution_logs
        }
