import json
import logging
import re
from typing import List, Dict, Any

from agents.base_agent import BaseAgent
from agents.models import (
    AgentContext,
    ExecutionPlan,
    RawOutput,
    ArtifactBody,
    Task,
    ExpectedOutput,
    ConfigurationError
)

logger = logging.getLogger("orchestra_learning_agent")

class LearningAgent(BaseAgent):
    """
    LearningAgent is a STRICT, read-only, observational agent.
    It extracts execution history patterns from execution_report, evaluation_report,
    and repair_decision artifacts without making code changes or running the pipeline.
    """

    def initialize(self, session_id: str, node_id: str):
        super().initialize(session_id, node_id)
        logger.info("LearningAgent: initialized")
        self.brain_client.log_audit_action(
            self.session_id,
            self.manifest.name,
            "learning_started",
            {"node_id": self.node_id}
        )

    def retrieve_context(self):
        super().retrieve_context()
        session_id = self.session_id
        session_artifacts = []
        if hasattr(self.brain_client, "artifacts"):
            session_artifacts = [a for a in self.brain_client.artifacts.values() if a.get("session_id") == session_id]
        elif hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "list_session_artifacts"):
            session_artifacts = self.brain_client.service.list_session_artifacts(session_id)
            
        session_decisions = []
        if hasattr(self.brain_client, "decisions"):
            session_decisions = [d for d in self.brain_client.decisions if d.get("session_id") == session_id]
        elif hasattr(self.brain_client, "service") and hasattr(self.brain_client.service, "list_session_decisions"):
            session_decisions = self.brain_client.service.list_session_decisions(session_id)
            
        from agents.models import ArtifactMetadata, DecisionSummary
        
        self.context.artifacts = [
            ArtifactMetadata(
                id=a.get("id", ""),
                session_id=a.get("session_id", ""),
                file_path=a.get("file_path", ""),
                version=a.get("version", 1),
                checksum=a.get("checksum", ""),
                type=a.get("type", ""),
                generated_by=a.get("generated_by", ""),
                depends_on=a.get("depends_on", []),
                used_by=a.get("used_by", [])
            )
            for a in session_artifacts
        ]
        
        self.context.decisions = [
            DecisionSummary(
                id=d.get("id", ""),
                node=d.get("node", ""),
                agent=d.get("agent", ""),
                title=d.get("title", ""),
                rationale=d.get("rationale", ""),
                confidence_score=d.get("confidence_score", 1.0),
                alternatives_considered=d.get("alternatives_considered", []),
                artifacts_produced=d.get("artifacts_produced", [])
            )
            for d in session_decisions
        ]
        logger.info("LearningAgent context retrieved successfully")

    def plan(self, context: AgentContext) -> ExecutionPlan:
        task1 = Task(
            id="read_pipeline_artifacts",
            description="Read PRD, System Design, Backend Scaffold, and Execution Report artifacts from the workspace",
            capability_required="read_workspace_file"
        )
        task2 = Task(
            id="extract_patterns",
            description="Extract failure, fix, and success patterns from system execution reports",
            capability_required="read_workspace_file"
        )
        return ExecutionPlan(
            tasks=[task1, task2],
            dependencies=[],
            required_skills=[],
            required_tools=["read_workspace_file"],
            expected_outputs=[
                ExpectedOutput(
                    artifact_type="learning_report",
                    description="Observational execution history learning report"
                )
            ],
            validation_rules=[],
            success_criteria=["Learning report is correctly structured and contains pattern extraction"]
        )

    def execute(self, plan: ExecutionPlan) -> RawOutput:
        # Collect artifacts metadata from context
        eval_artifact = next((a for a in self.context.artifacts if a.type == "evaluation_report"), None)
        repair_artifact = next((a for a in self.context.artifacts if a.type == "repair_decision"), None)
        exec_artifact = next((a for a in self.context.artifacts if a.type == "execution_report"), None)

        eval_path = eval_artifact.file_path if eval_artifact else "docs/05_evaluation_report.md"
        repair_path = repair_artifact.file_path if repair_artifact else "docs/06_repair_decision.json"
        exec_path = exec_artifact.file_path if exec_artifact else "docs/04_execution_report.md"

        # Read reports using ToolManager.read_workspace_file (ONLY read allowed)
        eval_content = ""
        repair_content = ""
        exec_content = ""

        try:
            eval_content = self.tools.read_workspace_file(eval_path)
            logger.info(f"Read evaluation report from {eval_path}")
        except Exception as e:
            logger.warning(f"Could not read evaluation report: {e}")

        try:
            repair_content = self.tools.read_workspace_file(repair_path)
            logger.info(f"Read repair decision from {repair_path}")
        except Exception as e:
            logger.warning(f"Could not read repair decision: {e}")

        try:
            exec_content = self.tools.read_workspace_file(exec_path)
            logger.info(f"Read execution report from {exec_path}")
        except Exception as e:
            logger.warning(f"Could not read execution report: {e}")

        # Parse structured repair decision JSON first (prefer structured data)
        repair_data = {}
        if repair_content:
            try:
                repair_data = json.loads(repair_content)
            except Exception as e:
                logger.warning(f"Failed to parse repair decision JSON: {e}")

        # Aggregate evidence
        issues_list = []
        fixes_list = []
        successes_list = []

        # Extract from structured repair decision
        if repair_data:
            issues_list.extend(repair_data.get("issues_detected", []))
            fixes_list.extend(repair_data.get("fixes_applied", []))

        # Extract from evaluation report markdown
        if eval_content:
            # Parse lines under ## 3. Issues Detected
            in_issues_section = False
            for line in eval_content.splitlines():
                line_stripped = line.strip()
                if "## 3. Issues Detected" in line_stripped:
                    in_issues_section = True
                elif line_stripped.startswith("## "):
                    in_issues_section = False
                elif in_issues_section and (line_stripped.startswith("-") or line_stripped.startswith("*")):
                    item = line_stripped.lstrip("-* ").strip()
                    if item and item.lower() != "none":
                        issues_list.append(item)

        # Extract from execution report markdown
        if exec_content:
            # Parse validation checks
            for line in exec_content.splitlines():
                line_stripped = line.strip()
                if "- [x]" in line_stripped or "- [ ]" in line_stripped:
                    check_name = line_stripped.split(":", 1)[0].replace("- [x]", "").replace("- [ ]", "").strip()
                    if "PASSED" in line_stripped or "SUCCESS" in line_stripped:
                        successes_list.append(f"Validation passed: {check_name}")
                    elif "FAILED" in line_stripped:
                        issues_list.append(f"Validation failed: {check_name}")

        # Count occurrences for multi-instance pattern extraction (do NOT infer from single occurrence)
        failure_counts = {"missing_endpoint": 0, "missing_entity": 0, "missing_service": 0, "config_failure": 0, "import_failure": 0}
        for issue in issues_list:
            issue_lower = issue.lower()
            if "api endpoint" in issue_lower or "endpoint" in issue_lower or "route" in issue_lower:
                failure_counts["missing_endpoint"] += 1
            if "entity" in issue_lower or "model" in issue_lower or "models.py" in issue_lower:
                failure_counts["missing_entity"] += 1
            if "service" in issue_lower or "services.py" in issue_lower:
                failure_counts["missing_service"] += 1
            if "config" in issue_lower or ".env" in issue_lower or "configuration" in issue_lower:
                failure_counts["config_failure"] += 1
            if "import" in issue_lower or "circular" in issue_lower:
                failure_counts["import_failure"] += 1

        fix_counts = {"added_entity": 0, "added_service": 0, "added_endpoint": 0, "config_repaired": 0}
        for fix in fixes_list:
            fix_lower = fix.lower()
            if "entity" in fix_lower or "models.py" in fix_lower or "model" in fix_lower:
                fix_counts["added_entity"] += 1
            if "service" in fix_lower or "services.py" in fix_lower:
                fix_counts["added_service"] += 1
            if "endpoint" in fix_lower or "api.py" in fix_lower or "route" in fix_lower:
                fix_counts["added_endpoint"] += 1
            if "config" in fix_lower or ".env" in fix_lower:
                fix_counts["config_repaired"] += 1

        # Extract Patterns if multi-instance (occurrence >= 2)
        failure_patterns = []
        if failure_counts["missing_endpoint"] >= 2:
            failure_patterns.append("Multiple missing API endpoint routes detected in backend application.")
        if failure_counts["missing_entity"] >= 2:
            failure_patterns.append("Multiple database entity/model omissions detected in models schema.")
        if failure_counts["missing_service"] >= 2:
            failure_patterns.append("Multiple missing business logic service classes detected in services module.")
        if failure_counts["import_failure"] >= 2:
            failure_patterns.append("Recurring validation failures due to incorrect imports or circular dependencies.")
        if failure_counts["config_failure"] >= 2:
            failure_patterns.append("Multiple environment configuration load failures or missing environment variables.")

        fix_patterns = []
        if fix_counts["added_entity"] >= 2:
            fix_patterns.append("Surgical generation of missing database entity models in models.py.")
        if fix_counts["added_service"] >= 2:
            fix_patterns.append("Surgical implementation of missing business logic service classes in services.py.")
        if fix_counts["added_endpoint"] >= 2:
            fix_patterns.append("Surgical definition of missing API router paths and methods in api.py.")
        if fix_counts["config_repaired"] >= 2:
            fix_patterns.append("Surgical update of environment configurations or env file attributes.")

        # Success Patterns: derived from validation successes
        success_patterns = []
        if len(successes_list) >= 2:
            success_patterns.append("FastAPI application bootstrapped successfully with valid Python imports and configuration.")
            success_patterns.append("API routers and paths registered correctly, passing basic runtime validation checks.")
        else:
            # Fallback based on session history / evaluation passing if score is high
            score_match = re.search(r"Overall Score:\s*([0-9.]+)", eval_content)
            if score_match and float(score_match.group(1)) >= 8.0:
                success_patterns.append("High consistency and alignment between system design blueprint and backend implementation.")

        # Recommendations based on failure patterns
        recommendations = []
        if "Multiple database entity/model omissions detected in models schema." in failure_patterns:
            recommendations.append("Pre-declare all database entities and models in the system design blueprint to prevent repair loops.")
        if "Multiple missing API endpoint routes detected in backend application." in failure_patterns:
            recommendations.append("Ensure all design routes are completely mapped and implemented in the router layer.")
        if "Multiple environment configuration load failures or missing environment variables." in failure_patterns:
            recommendations.append("Configure all required environment variables in backend/.env prior to validation stage.")
        
        # Always include a general observational recommendation
        recommendations.append("Maintain consistent design and schema definitions between Blueprint and Implementation phases.")

        # Record mock model call metrics
        self.metrics.record_model_call(
            tokens_in=80,
            tokens_out=180,
            latency_ms=90.0,
            prompt_chars=400
        )

        return RawOutput(
            content_blocks={
                "failure_patterns": failure_patterns,
                "fix_patterns": fix_patterns,
                "success_patterns": success_patterns,
                "recommendations_for_future_runs": recommendations
            },
            decision_records=[],  # MUST NOT modify Project Brain decision logs
            flags=[]
        )

    def generate_artifacts(self, raw: RawOutput) -> List[ArtifactBody]:
        content_dict = {
            "failure_patterns": raw.content_blocks.get("failure_patterns", []),
            "fix_patterns": raw.content_blocks.get("fix_patterns", []),
            "success_patterns": raw.content_blocks.get("success_patterns", []),
            "recommendations_for_future_runs": raw.content_blocks.get("recommendations_for_future_runs", [])
        }
        content = json.dumps(content_dict, indent=2)
        ab = ArtifactBody(
            content=content,
            artifact_type="learning_report",
            file_path="docs/07_learning_report.json",
            decisions=[]  # Crucial: NO decisions logged to Project Brain
        )
        return [ab]

    def self_evaluate(self, artifacts: List[ArtifactBody]) -> Dict[str, Any]:
        for art in artifacts:
            try:
                data = json.loads(art.content)
                required_fields = ["failure_patterns", "fix_patterns", "success_patterns", "recommendations_for_future_runs"]
                if not all(field in data for field in required_fields):
                    return {"passed": False, "failed_rules": ["missing-required-fields"]}
            except Exception:
                return {"passed": False, "failed_rules": ["invalid-json-content"]}
        return {"passed": True, "failed_rules": []}

    def persist_results(self):
        # Write output artifact to workspace
        for art in self.artifacts_body:
            try:
                self.tools.write_workspace_file(art.file_path, art.content)
                logger.info(f"Persisted artifact to workspace: {art.file_path}")
            except Exception as e:
                logger.warning(f"Failed to write artifact '{art.file_path}' to workspace: {e}")
        
        # Save in Brain database (which does not affect runtime state or create decisions)
        super().persist_results()
        
        self.brain_client.log_audit_action(
            self.session_id,
            self.manifest.name,
            "learning_completed",
            {"node_id": self.node_id}
        )
        logger.info("LearningAgent: results persisted and completed")
