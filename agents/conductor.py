import uuid
import logging
from typing import Dict, Any, Optional
from agents.factory import AgentFactory
from agents.session_adapter import SessionStateAdapter
from agents.brain_client import BrainServiceClient

logger = logging.getLogger("orchestra_conductor")

class Conductor:
    """
    Root orchestration agent entry point for Orchestra AI.
    Coordinates requests by dispatching to specialist agents,
    managing runtime session state, and persisting results.
    """
    def __init__(self, brain_client: BrainServiceClient, agent_factory: AgentFactory):
        self.brain_client = brain_client
        self.agent_factory = agent_factory
        
        # Ensure PlanningAgent is registered in factory
        from agents.planning import PlanningAgent
        if "Planning Agent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("Planning Agent", PlanningAgent)
        if "PlanningAgent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("PlanningAgent", PlanningAgent)

        # Ensure BlueprintAgent is registered in factory
        from agents.blueprint import BlueprintAgent
        if "Blueprint Agent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("Blueprint Agent", BlueprintAgent)
        if "BlueprintAgent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("BlueprintAgent", BlueprintAgent)
        if "blueprint_agent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("blueprint_agent", BlueprintAgent)
        if "blueprint_design" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("blueprint_design", BlueprintAgent)

        # Ensure ImplementationAgent is registered in factory using role-based registry only
        from agents.implementation import ImplementationAgent
        if "implementation_agent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("implementation_agent", ImplementationAgent)

        # Ensure RuntimeValidationAgent is registered in factory
        from agents.runtime_validation import RuntimeValidationAgent
        if "runtime_validation_agent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("runtime_validation_agent", RuntimeValidationAgent)

    def run(self, product_idea: str, project_id: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Main entry point for coordinating a request.
        """
        logger.info("Conductor execution started.")
        
        # 1. Project and Session Resolution
        if not project_id:
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "create_project"):
                try:
                    project = self.brain_client.service.create_project(
                        name="Auto-Generated Project",
                        description=f"Project created for request: {product_idea[:50]}"
                    )
                    project_id = project["id"]
                    logger.info(f"Project created in Project Brain with ID: {project_id}")
                except Exception as e:
                    logger.warning(f"Failed to create project through service: {e}")
                    project_id = f"proj-{uuid.uuid4().hex[:8]}"
            else:
                project_id = f"proj-{uuid.uuid4().hex[:8]}"
                logger.info(f"Using generated project ID: {project_id}")
        else:
            logger.info(f"Using provided project ID: {project_id}")
        
        planning_node_id = "planning_node"
        blueprint_node_id = "blueprint_node"
        implementation_node_id = "implementation_node"
        validation_node_id = "validation_node"

        if not session_id:
            session_id = f"sess-{uuid.uuid4().hex[:8]}"
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "create_session"):
                try:
                    pipeline = {
                        "nodes": [
                            {"id": planning_node_id, "name": "Planning", "agent": "Planning Agent", "status": "PENDING"},
                            {"id": blueprint_node_id, "name": "Blueprint", "agent": "Blueprint Agent", "status": "PENDING"},
                            {"id": implementation_node_id, "name": "Implementation", "agent": "implementation_agent", "status": "PENDING"},
                            {"id": validation_node_id, "name": "Validation", "agent": "runtime_validation_agent", "status": "PENDING"}
                        ],
                        "edges": [
                            {"source": planning_node_id, "target": blueprint_node_id},
                            {"source": blueprint_node_id, "target": implementation_node_id},
                            {"source": implementation_node_id, "target": validation_node_id}
                        ],
                        "history": []
                    }
                    self.brain_client.service.create_session(project_id=project_id, git_commit_hash=None, dag=pipeline)
                    logger.info(f"Session created in Project Brain with ID: {session_id}")
                except Exception as e:
                    logger.warning(f"Failed to create session through service: {e}")
            else:
                logger.info(f"Using generated session ID: {session_id}")
        else:
            logger.info(f"Using provided session ID: {session_id}")

        # 2. Initialize runtime session state
        state_dict = {
            "session_id": session_id,
            "project_id": project_id,
            f"node_{planning_node_id}_task_instruction": product_idea,
            f"node_{planning_node_id}_status": "Pending",
            f"node_{blueprint_node_id}_task_instruction": "Generate system design blueprint based on PRD",
            f"node_{blueprint_node_id}_status": "Pending",
            f"node_{implementation_node_id}_task_instruction": "Generate backend code scaffold based on system design blueprint",
            f"node_{implementation_node_id}_status": "Pending",
            f"node_{validation_node_id}_task_instruction": "Validate the generated backend scaffold by executing it inside the sandbox",
            f"node_{validation_node_id}_status": "Pending",
            "workflow_state": "IN_PROGRESS",
            "workflow_active_nodes": [planning_node_id],
            "workflow_completed_nodes": []
        }
        session_state = SessionStateAdapter(state_dict)
        logger.info("Runtime session state initialized.")

        # 3. Resolve Planning Agent through AgentFactory using role/capability-based registry lookup
        capability = "prd"
        logger.info(f"Resolving specialist agent for capability '{capability}'...")
        try:
            agent = self.agent_factory.create_for_capability(
                capability=capability,
                session_id=session_id,
                node_id=planning_node_id,
                session_state=session_state
            )
            logger.info(f"Resolved agent '{agent.manifest.name}' for capability '{capability}'")
        except Exception as e:
            logger.error(f"Agent resolution failed for capability '{capability}': {e}")
            raise e

        # 4. Execute PlanningAgent through BaseAgent lifecycle
        logger.info(f"Executing agent '{agent.manifest.name}' lifecycle for node '{planning_node_id}'...")
        try:
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                try:
                    self.brain_client.service.update_session(session_id, {"active_node": planning_node_id, "status": "IN_PROGRESS"})
                except Exception as e:
                    logger.warning(f"Failed to update session active node: {e}")

            lifecycle_result = agent.execute_lifecycle(session_id=session_id, node_id=planning_node_id)
            logger.info(f"Agent '{agent.manifest.name}' lifecycle executed successfully.")
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                try:
                    self.brain_client.service.update_session(session_id, {"status": "FAILED"})
                except Exception:
                    pass
            raise e

        # 4b. Execute BlueprintAgent through BaseAgent lifecycle
        if lifecycle_result.get("status") != "success":
            raise Exception("Planning Agent execution failed, halting workflow.")

        session_state.set_node_status(planning_node_id, "Completed")
        session_state._state["workflow_completed_nodes"].append(planning_node_id)
        session_state._state["workflow_active_nodes"] = [blueprint_node_id]

        blueprint_capability = "blueprint_agent"
        logger.info(f"Resolving specialist agent for capability '{blueprint_capability}'...")
        try:
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                try:
                    self.brain_client.service.update_session(session_id, {"active_node": blueprint_node_id})
                except Exception as e:
                    logger.warning(f"Failed to update session active node to blueprint_node: {e}")

            blueprint_agent = self.agent_factory.create_for_capability(
                capability=blueprint_capability,
                session_id=session_id,
                node_id=blueprint_node_id,
                session_state=session_state
            )
            logger.info(f"Resolved agent '{blueprint_agent.manifest.name}' for capability '{blueprint_capability}'")

            blueprint_result = blueprint_agent.execute_lifecycle(session_id=session_id, node_id=blueprint_node_id)
            logger.info(f"Agent '{blueprint_agent.manifest.name}' lifecycle executed successfully.")
        except Exception as e:
            logger.error(f"Blueprint Agent execution failed: {e}")
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                try:
                    self.brain_client.service.update_session(session_id, {"status": "FAILED"})
                except Exception:
                    pass
            raise e

        # 4c. Execute ImplementationAgent through BaseAgent lifecycle
        if blueprint_result.get("status") != "success":
            raise Exception("Blueprint Agent execution failed, halting workflow.")

        session_state.set_node_status(blueprint_node_id, "Completed")
        session_state._state["workflow_completed_nodes"].append(blueprint_node_id)
        session_state._state["workflow_active_nodes"] = [implementation_node_id]

        implementation_capability = "implementation_agent"
        logger.info(f"Resolving specialist agent for capability '{implementation_capability}'...")
        try:
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                try:
                    self.brain_client.service.update_session(session_id, {"active_node": implementation_node_id})
                except Exception as e:
                    logger.warning(f"Failed to update session active node to implementation_node: {e}")

            implementation_agent = self.agent_factory.create_for_capability(
                capability=implementation_capability,
                session_id=session_id,
                node_id=implementation_node_id,
                session_state=session_state
            )
            logger.info(f"Resolved agent '{implementation_agent.manifest.name}' for capability '{implementation_capability}'")

            implementation_result = implementation_agent.execute_lifecycle(session_id=session_id, node_id=implementation_node_id)
            logger.info(f"Agent '{implementation_agent.manifest.name}' lifecycle executed successfully.")
        except Exception as e:
            logger.error(f"Implementation Agent execution failed: {e}")
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                try:
                    self.brain_client.service.update_session(session_id, {"status": "FAILED"})
                except Exception:
                    pass
            raise e

        session_state.set_node_status(implementation_node_id, "Completed")
        session_state._state["workflow_completed_nodes"].append(implementation_node_id)
        session_state._state["workflow_active_nodes"] = [validation_node_id]

        # 4d. Execute RuntimeValidationAgent through BaseAgent lifecycle
        if implementation_result.get("status") != "success":
            raise Exception("Implementation Agent execution failed, halting workflow.")

        validation_capability = "runtime_validation_agent"
        logger.info(f"Resolving specialist agent for capability '{validation_capability}'...")
        try:
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                try:
                    self.brain_client.service.update_session(session_id, {"active_node": validation_node_id})
                except Exception as e:
                    logger.warning(f"Failed to update session active node to validation_node: {e}")

            validation_agent = self.agent_factory.create_for_capability(
                capability=validation_capability,
                session_id=session_id,
                node_id=validation_node_id,
                session_state=session_state
            )
            logger.info(f"Resolved agent '{validation_agent.manifest.name}' for capability '{validation_capability}'")

            validation_result = validation_agent.execute_lifecycle(session_id=session_id, node_id=validation_node_id)
            logger.info(f"Agent '{validation_agent.manifest.name}' lifecycle executed successfully.")
        except Exception as e:
            logger.error(f"Runtime Validation Agent execution failed: {e}")
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                try:
                    self.brain_client.service.update_session(session_id, {"status": "FAILED"})
                except Exception:
                    pass
            raise e

        session_state.set_node_status(validation_node_id, "Completed")
        session_state._state["workflow_completed_nodes"].append(validation_node_id)
        session_state._state["workflow_active_nodes"] = []

        # 5. Persist final session updates and retrieve outcomes from Project Brain
        if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
            try:
                self.brain_client.service.update_session(session_id, {"status": "COMPLETED"})
                logger.info("Session status updated to COMPLETED in Project Brain.")
            except Exception as e:
                logger.warning(f"Failed to finalize session status: {e}")

        # Retrieve stored artifacts for this session to construct final response
        artifacts = []
        if hasattr(self.brain_client, "artifacts"):
            artifacts = [a for a in self.brain_client.artifacts.values() if a.get("session_id") == session_id]
        elif hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "list_session_artifacts"):
            artifacts = self.brain_client.service.list_session_artifacts(session_id)

        # Retrieve stored decisions for this session
        decisions = []
        if hasattr(self.brain_client, "decisions"):
            decisions = [d for d in self.brain_client.decisions if d.get("session_id") == session_id]
        elif hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "list_session_decisions"):
            decisions = self.brain_client.service.list_session_decisions(session_id)

        logger.info(f"Persisted {len(artifacts)} artifacts and {len(decisions)} decisions to Project Brain.")

        # 6. Return final structured response
        response = {
            "session_id": session_id,
            "project_id": project_id,
            "status": "success" if (
                lifecycle_result.get("status") == "success" and 
                blueprint_result.get("status") == "success" and 
                implementation_result.get("status") == "success" and
                validation_result.get("status") == "success"
            ) else "failed",
            "state": session_state._state,
            "artifacts": artifacts,
            "decisions": decisions,
            "metrics": validation_result.get("metrics", {})
        }
        logger.info("Final response constructed and returned.")
        return response

