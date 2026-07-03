import uuid
import logging
import json
import os
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

        # Ensure EvaluationAgent is registered in factory
        from agents.evaluation import EvaluationAgent
        if "evaluation_agent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("evaluation_agent", EvaluationAgent)

        # Ensure RepairAgent is registered in factory
        from agents.repair import RepairAgent
        if "repair_agent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("repair_agent", RepairAgent)

        # Ensure LearningAgent is registered in factory
        from agents.learning import LearningAgent
        if "learning_agent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("learning_agent", LearningAgent)

        # Ensure PredictiveAgent is registered in factory
        from agents.predictive import PredictiveAgent
        if "predictive_agent" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("predictive_agent", PredictiveAgent)
        if "prediction_report" not in self.agent_factory.class_registry:
            self.agent_factory.register_agent_class("prediction_report", PredictiveAgent)

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
        predictive_node_id = "predictive_node"
        validation_node_id = "validation_node"
        evaluation_node_id = "evaluation_node"
        repair_node_id = "repair_node"
        learning_node_id = "learning_node"

        if not session_id:
            session_id = f"sess-{uuid.uuid4().hex[:8]}"
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "create_session"):
                try:
                    pipeline = {
                        "nodes": [
                            {"id": planning_node_id, "name": "Planning", "agent": "Planning Agent", "status": "PENDING"},
                            {"id": blueprint_node_id, "name": "Blueprint", "agent": "Blueprint Agent", "status": "PENDING"},
                            {"id": implementation_node_id, "name": "Implementation", "agent": "implementation_agent", "status": "PENDING"},
                            {"id": predictive_node_id, "name": "Predictive", "agent": "predictive_agent", "status": "PENDING"},
                            {"id": validation_node_id, "name": "Validation", "agent": "runtime_validation_agent", "status": "PENDING"},
                            {"id": evaluation_node_id, "name": "Evaluation", "agent": "evaluation_agent", "status": "PENDING"},
                            {"id": repair_node_id, "name": "Repair", "agent": "repair_agent", "status": "PENDING"},
                            {"id": learning_node_id, "name": "Learning", "agent": "learning_agent", "status": "PENDING"}
                        ],
                        "edges": [
                            {"source": planning_node_id, "target": blueprint_node_id},
                            {"source": blueprint_node_id, "target": implementation_node_id},
                            {"source": implementation_node_id, "target": predictive_node_id},
                            {"source": predictive_node_id, "target": validation_node_id},
                            {"source": validation_node_id, "target": evaluation_node_id},
                            {"source": evaluation_node_id, "target": repair_node_id},
                            {"source": repair_node_id, "target": learning_node_id}
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
            f"node_{predictive_node_id}_task_instruction": "Analyze system design and historical learning data to predict failures before execution",
            f"node_{predictive_node_id}_status": "Pending",
            f"node_{validation_node_id}_task_instruction": "Validate the generated backend scaffold by executing it inside the sandbox",
            f"node_{validation_node_id}_status": "Pending",
            f"node_{evaluation_node_id}_task_instruction": "Evaluate the pipeline quality using existing artifacts",
            f"node_{evaluation_node_id}_status": "Pending",
            f"node_{repair_node_id}_task_instruction": "Surgically repair any failure found in implementation or validation",
            f"node_{repair_node_id}_status": "Pending",
            f"node_{learning_node_id}_task_instruction": "Extract execution history patterns from execution_report, evaluation_report, and repair_decision artifacts",
            f"node_{learning_node_id}_status": "Pending",
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

        # 4c. Execution Loop (Implementation -> Validation -> Evaluation -> Repair)
        if blueprint_result.get("status") != "success":
            raise Exception("Blueprint Agent execution failed, halting workflow.")

        session_state.set_node_status(blueprint_node_id, "Completed")
        session_state._state["workflow_completed_nodes"].append(blueprint_node_id)

        loop_count = 0
        max_loops = 3
        next_node = implementation_node_id

        implementation_result = {"status": "pending"}
        predictive_result = {"status": "pending"}
        validation_result = {"status": "pending"}
        evaluation_result = {"status": "pending"}
        repair_result = {"status": "pending"}

        while loop_count < max_loops:
            logger.info(f"--- Pipeline Loop Execution {loop_count + 1}/{max_loops} (starting at node '{next_node}') ---")

            if next_node == implementation_node_id:
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
                if implementation_node_id not in session_state._state["workflow_completed_nodes"]:
                    session_state._state["workflow_completed_nodes"].append(implementation_node_id)
                next_node = predictive_node_id

            if next_node == predictive_node_id:
                session_state._state["workflow_active_nodes"] = [predictive_node_id]
                if implementation_result.get("status") != "success":
                    raise Exception("Implementation Agent execution failed, halting workflow.")

                predictive_capability = "prediction_report"
                logger.info(f"Resolving specialist agent for capability '{predictive_capability}'...")
                try:
                    if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                        try:
                            self.brain_client.service.update_session(session_id, {"active_node": predictive_node_id})
                        except Exception as e:
                            logger.warning(f"Failed to update session active node to predictive_node: {e}")

                    predictive_agent = self.agent_factory.create_for_capability(
                        capability=predictive_capability,
                        session_id=session_id,
                        node_id=predictive_node_id,
                        session_state=session_state
                    )
                    logger.info(f"Resolved agent '{predictive_agent.manifest.name}' for capability '{predictive_capability}'")

                    predictive_result = predictive_agent.execute_lifecycle(session_id=session_id, node_id=predictive_node_id)
                    logger.info(f"Agent '{predictive_agent.manifest.name}' lifecycle executed successfully.")
                except Exception as e:
                    logger.error(f"Predictive Agent execution failed: {e}")
                    if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                        try:
                            self.brain_client.service.update_session(session_id, {"status": "FAILED"})
                        except Exception:
                            pass
                    raise e

                session_state.set_node_status(predictive_node_id, "Completed")
                if predictive_node_id not in session_state._state["workflow_completed_nodes"]:
                    session_state._state["workflow_completed_nodes"].append(predictive_node_id)
                next_node = validation_node_id

            if next_node == validation_node_id:
                session_state._state["workflow_active_nodes"] = [validation_node_id]
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
                if validation_node_id not in session_state._state["workflow_completed_nodes"]:
                    session_state._state["workflow_completed_nodes"].append(validation_node_id)
                next_node = evaluation_node_id

            if next_node == evaluation_node_id:
                session_state._state["workflow_active_nodes"] = [evaluation_node_id]
                if validation_result.get("status") != "success":
                    raise Exception("Runtime Validation Agent execution failed, halting workflow.")

                evaluation_capability = "evaluation_agent"
                logger.info(f"Resolving specialist agent for capability '{evaluation_capability}'...")
                try:
                    if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                        try:
                            self.brain_client.service.update_session(session_id, {"active_node": evaluation_node_id})
                        except Exception as e:
                            logger.warning(f"Failed to update session active node to evaluation_node: {e}")

                    evaluation_agent = self.agent_factory.create_for_capability(
                        capability=evaluation_capability,
                        session_id=session_id,
                        node_id=evaluation_node_id,
                        session_state=session_state
                    )
                    logger.info(f"Resolved agent '{evaluation_agent.manifest.name}' for capability '{evaluation_capability}'")

                    evaluation_result = evaluation_agent.execute_lifecycle(session_id=session_id, node_id=evaluation_node_id)
                    logger.info(f"Agent '{evaluation_agent.manifest.name}' lifecycle executed successfully.")
                except Exception as e:
                    logger.error(f"Evaluation Agent execution failed: {e}")
                    if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                        try:
                            self.brain_client.service.update_session(session_id, {"status": "FAILED"})
                        except Exception:
                            pass
                    raise e

                session_state.set_node_status(evaluation_node_id, "Completed")
                if evaluation_node_id not in session_state._state["workflow_completed_nodes"]:
                    session_state._state["workflow_completed_nodes"].append(evaluation_node_id)
                next_node = repair_node_id

            if next_node == repair_node_id:
                session_state._state["workflow_active_nodes"] = [repair_node_id]
                if evaluation_result.get("status") != "success":
                    raise Exception("Evaluation Agent execution failed, halting workflow.")

                repair_capability = "repair_agent"
                logger.info(f"Resolving specialist agent for capability '{repair_capability}'...")
                try:
                    if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                        try:
                            self.brain_client.service.update_session(session_id, {"active_node": repair_node_id})
                        except Exception as e:
                            logger.warning(f"Failed to update session active node to repair_node: {e}")

                    repair_agent = self.agent_factory.create_for_capability(
                        capability=repair_capability,
                        session_id=session_id,
                        node_id=repair_node_id,
                        session_state=session_state
                    )
                    logger.info(f"Resolved agent '{repair_agent.manifest.name}' for capability '{repair_capability}'")

                    repair_result = repair_agent.execute_lifecycle(session_id=session_id, node_id=repair_node_id)
                    logger.info(f"Agent '{repair_agent.manifest.name}' lifecycle executed successfully.")
                except Exception as e:
                    logger.error(f"Repair Agent execution failed: {e}")
                    if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                        try:
                            self.brain_client.service.update_session(session_id, {"status": "FAILED"})
                        except Exception:
                            pass
                    raise e

                session_state.set_node_status(repair_node_id, "Completed")
                if repair_node_id not in session_state._state["workflow_completed_nodes"]:
                    session_state._state["workflow_completed_nodes"].append(repair_node_id)
                session_state._state["workflow_active_nodes"] = []

                # Read docs/06_repair_decision.json to decide reroute
                repair_decision = {}
                try:
                    decision_content = self._read_workspace_file("docs/06_repair_decision.json")
                    repair_decision = json.loads(decision_content)
                except Exception as e:
                    logger.warning(f"Failed to read repair decision JSON: {e}")

                retry_required = repair_decision.get("retry_required", False)
                issues_detected = repair_decision.get("issues_detected", [])

                if retry_required and loop_count + 1 < max_loops:
                    loop_count += 1
                    
                    # Conductor Rerouting Rules:
                    # Rerun implementation_node if structural components are missing
                    # Rerun validation_node if runtime/validation failures exist
                    structural_missing = False
                    for issue in issues_detected:
                        issue_lower = issue.lower()
                        if "missing api endpoint" in issue_lower or "missing entity" in issue_lower or "missing service" in issue_lower:
                            structural_missing = True
                            break

                    if structural_missing:
                        next_node = implementation_node_id
                        logger.info("Structural components missing. Rerunning implementation_node.")
                    else:
                        next_node = validation_node_id
                        logger.info("Runtime/validation failures exist. Rerunning validation_node.")

                    # Reset nodes that will be rerun
                    nodes_to_reset = []
                    if next_node == implementation_node_id:
                        nodes_to_reset = [implementation_node_id, predictive_node_id, validation_node_id, evaluation_node_id, repair_node_id]
                    else:
                        nodes_to_reset = [validation_node_id, evaluation_node_id, repair_node_id]

                    for nid in nodes_to_reset:
                        if nid in session_state._state["workflow_completed_nodes"]:
                            session_state._state["workflow_completed_nodes"].remove(nid)
                        session_state.set_node_status(nid, "Pending")
                else:
                    # Exit loop
                    break

        # 4e. Execute LearningAgent through BaseAgent lifecycle
        learning_result = {"status": "pending"}
        session_state._state["workflow_active_nodes"] = [learning_node_id]
        learning_capability = "learning_agent"
        logger.info(f"Resolving specialist agent for capability '{learning_capability}'...")
        try:
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                try:
                    self.brain_client.service.update_session(session_id, {"active_node": learning_node_id})
                except Exception as e:
                    logger.warning(f"Failed to update session active node to learning_node: {e}")

            learning_agent = self.agent_factory.create_for_capability(
                capability=learning_capability,
                session_id=session_id,
                node_id=learning_node_id,
                session_state=session_state
            )
            logger.info(f"Resolved agent '{learning_agent.manifest.name}' for capability '{learning_capability}'")

            learning_result = learning_agent.execute_lifecycle(session_id=session_id, node_id=learning_node_id)
            logger.info(f"Agent '{learning_agent.manifest.name}' lifecycle executed successfully.")
        except Exception as e:
            logger.error(f"Learning Agent execution failed: {e}")
            if hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "update_session"):
                try:
                    self.brain_client.service.update_session(session_id, {"status": "FAILED"})
                except Exception:
                    pass
            raise e

        session_state.set_node_status(learning_node_id, "Completed")
        if learning_node_id not in session_state._state["workflow_completed_nodes"]:
            session_state._state["workflow_completed_nodes"].append(learning_node_id)
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
                predictive_result.get("status") == "success" and
                validation_result.get("status") == "success" and
                evaluation_result.get("status") == "success" and
                repair_result.get("status") == "success" and
                learning_result.get("status") == "success"
            ) else "failed",
            "state": session_state._state,
            "artifacts": artifacts,
            "decisions": decisions,
            "metrics": learning_result.get("metrics", {})
        }
        logger.info("Final response constructed and returned.")
        return response

    def _read_workspace_file(self, path: str) -> str:
        if hasattr(self.agent_factory, "mcp_resolver") and self.agent_factory.mcp_resolver:
            try:
                res = self.agent_factory.mcp_resolver.call_tool("filesystem", "read_file", {"path": path})
                if isinstance(res, dict) and "content" in res:
                    return res["content"]
                return str(res)
            except Exception:
                pass
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        raise Exception(f"File not found: {path}")

