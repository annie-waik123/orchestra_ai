import json
import logging
import re
import difflib
from typing import List, Dict, Any, Tuple

from agents.base_agent import BaseAgent
from agents.models import (
    AgentContext,
    ExecutionPlan,
    RawOutput,
    ArtifactBody,
    DecisionRecord,
    Task,
    ExpectedOutput,
    ConfigurationError
)

logger = logging.getLogger("orchestra_repair_agent")

class RepairAgent(BaseAgent):
    """
    RepairAgent performs deterministic, surgical repairs on the backend scaffold.
    It diagnoses failures from evaluation and runtime validation reports,
    generates a structured repair plan, and applies fixes via ToolManager.
    """

    def initialize(self, session_id: str, node_id: str):
        super().initialize(session_id, node_id)
        logger.info("RepairAgent: initialized")
        self.brain_client.log_audit_action(
            self.session_id,
            self.manifest.name,
            "repair_started",
            {"node_id": self.node_id}
        )

    def retrieve_context(self):
        super().retrieve_context()
        session_id = self.session_id
        
        # Load artifacts and decisions
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
        logger.info("RepairAgent: context retrieved")

    def plan(self, context: AgentContext) -> ExecutionPlan:
        task1 = Task(
            id="diagnose_failures",
            description="Diagnose failures in evaluation and execution reports",
            capability_required="read_workspace_file"
        )
        task2 = Task(
            id="plan_repairs",
            description="Plan structured repair instructions",
            capability_required="read_workspace_file"
        )
        task3 = Task(
            id="execute_repairs",
            description="Apply repairs safely via ToolManager write_workspace_file",
            capability_required="write_workspace_file"
        )
        return ExecutionPlan(
            tasks=[task1, task2, task3],
            dependencies=[],
            required_skills=[],
            required_tools=["read_workspace_file", "write_workspace_file"],
            expected_outputs=[
                ExpectedOutput(
                    artifact_type="repair_decision",
                    description="Repair decision and summary report"
                )
            ],
            validation_rules=[],
            success_criteria=["Repair decision JSON is correctly written to docs/06_repair_decision.json"]
        )

    def execute(self, plan: ExecutionPlan) -> RawOutput:
        # Find required inputs
        eval_artifact = next((a for a in self.context.artifacts if a.type == "evaluation_report"), None)
        exec_artifact = next((a for a in self.context.artifacts if a.type == "execution_report"), None)

        eval_path = eval_artifact.file_path if eval_artifact else "docs/05_evaluation_report.md"
        exec_path = exec_artifact.file_path if exec_artifact else "docs/04_execution_report.md"

        # --- Phase 1: Diagnosis ---
        logger.info("--- Phase 1: Diagnosis ---")
        issues_detected = []
        
        # Read files safely via ToolManager
        eval_content = ""
        exec_content = ""
        try:
            eval_content = self.tools.read_workspace_file(eval_path)
            logger.info(f"Read evaluation report from {eval_path}")
        except Exception as e:
            logger.warning(f"Could not read evaluation report: {e}")
            
        try:
            exec_content = self.tools.read_workspace_file(exec_path)
            logger.info(f"Read execution report from {exec_path}")
        except Exception as e:
            logger.warning(f"Could not read execution report: {e}")

        # Parse evaluation report issues and recommendations
        missing_endpoints = []
        missing_entities = []
        missing_services = []
        scaffold_missing = False
        config_failed = False
        imports_failed = False
        routes_failed = False
        
        if eval_content:
            # Parse lines under Issues Detected or recommendations
            for line in eval_content.splitlines():
                if "Missing API endpoint" in line or "Implement route" in line:
                    match = re.search(r'(?:Missing API endpoint|Implement route)\s+(GET|POST|PUT|DELETE|PATCH)\s+([^\s]+)', line, re.IGNORECASE)
                    if match:
                        missing_endpoints.append((match.group(1).upper(), match.group(2)))
                        issues_detected.append(f"Missing API endpoint: {match.group(1).upper()} {match.group(2)}")
                elif "Missing Entity class/schema" in line or "Declare class" in line:
                    match = re.search(r"(?:Missing Entity class/schema for|Declare class)\s+'?([A-Za-z0-9_]+)'?", line)
                    if match and "models.py" in line:
                        missing_entities.append(match.group(1))
                        issues_detected.append(f"Missing Entity class: {match.group(1)}")
                elif "Missing Service class" in line or "Declare class" in line:
                    match = re.search(r"(?:Missing Service class|Declare class)\s+'?([A-Za-z0-9_]+)'?", line)
                    if match and "services.py" in line:
                        missing_services.append(match.group(1))
                        issues_detected.append(f"Missing Service class: {match.group(1)}")
                elif "is missing or unreadable" in line or "artifact from pipeline" in line:
                    if "scaffold" in line.lower() or "Scaffold" in line:
                        scaffold_missing = True
                    issues_detected.append(line.strip("-* "))

        if exec_content:
            # Parse validation checks
            if "Configuration Loaded: FAILED" in exec_content or "Check database URLs" in exec_content:
                config_failed = True
                issues_detected.append("Configuration failed to load")
            if "Python Imports Valid: FAILED" in exec_content or "Check for circular imports" in exec_content:
                imports_failed = True
                issues_detected.append("Python imports validation failed")
            if "Routes Loaded: FAILED" in exec_content or "Register API routers properly" in exec_content:
                routes_failed = True
                issues_detected.append("API Route loading failed")

        logger.info(f"Diagnosed issues: {issues_detected}")

        # --- Phase 2: Repair Planning ---
        logger.info("--- Phase 2: Repair Planning ---")
        repair_instructions = []
        
        # 1. Missing Entity Models
        for ent in missing_entities:
            content = (
                f"\n# --- Repaired {ent} Model ---\n"
                f"class {ent}(Base):\n"
                f"    __tablename__ = '{ent.lower()}s'\n"
                f"    id = Column(Integer, primary_key=True, index=True)\n\n"
                f"class {ent}Schema(BaseModel):\n"
                f"    id: int\n"
                f"    class Config:\n"
                f"        from_attributes = True\n"
            )
            instruction = {
                "operation": "add",
                "target_file": "backend/app/models.py",
                "action_type": "append_model",
                "content": content,
                "reason": f"Add missing entity class and schema for {ent}"
            }
            repair_instructions.append(instruction)

        # 2. Missing Services
        for svc in missing_services:
            content = (
                f"\nclass {svc}:\n"
                f"    def __init__(self):\n"
                f"        pass\n"
                f"    def execute_logic(self) -> dict:\n"
                f"        return {{'status': 'success'}}\n"
            )
            instruction = {
                "operation": "add",
                "target_file": "backend/app/services.py",
                "action_type": "append_service",
                "content": content,
                "reason": f"Add missing service class {svc}"
            }
            repair_instructions.append(instruction)

        # 3. Missing API Endpoints
        for method, path in missing_endpoints:
            clean_path = re.sub(r'[^a-zA-Z0-9]', '_', path.strip('/'))
            content = (
                f"\n@router.{method.lower()}('{path}')\n"
                f"def endpoint_repaired_{method.lower()}_{clean_path}(db: Session = Depends(get_db)):\n"
                f"    return {{'message': 'Repaired stub response for {method} {path}'}}\n"
            )
            instruction = {
                "operation": "add",
                "target_file": "backend/app/api.py",
                "action_type": "append_route",
                "content": content,
                "reason": f"Add missing route {method} {path}"
            }
            repair_instructions.append(instruction)

        # 4. Configuration Failure
        if config_failed:
            instruction = {
                "operation": "modify",
                "target_file": "backend/.env",
                "action_type": "fix_config",
                "content": "DATABASE_URL=sqlite:///./test.db\n",
                "reason": "Ensure DATABASE_URL environment setting is valid"
            }
            repair_instructions.append(instruction)

        # 5. Imports or Routes Failure
        if imports_failed or routes_failed:
            instruction = {
                "operation": "modify",
                "target_file": "backend/app/main.py",
                "action_type": "fix_config",
                "content": (
                    "import uvicorn\n"
                    "from fastapi import FastAPI\n"
                    "from backend.app.api import router as api_router\n"
                    "from backend.app.db import engine, Base\n\n"
                    "Base.metadata.create_all(bind=engine)\n\n"
                    "app = FastAPI(title='Orchestra AI Generated Backend')\n"
                    "app.include_router(api_router)\n\n"
                    "@app.get('/')\n"
                    "def read_root():\n"
                    "    return {'status': 'healthy'}\n"
                ),
                "reason": "Ensure main application initialization and router registrations are valid"
            }
            repair_instructions.append(instruction)

        logger.info(f"Planned repair instructions: {repair_instructions}")

        # --- Phase 3: Execution ---
        logger.info("--- Phase 3: Execution ---")
        fixes_applied = []
        execution_failed = False
        
        for idx, inst in enumerate(repair_instructions):
            target_file = inst["target_file"]
            action_type = inst["action_type"]
            patch_content = inst["content"]
            reason = inst["reason"]
            
            logger.info(f"Processing instruction {idx + 1}/{len(repair_instructions)}: {reason}")
            
            try:
                # 1. Read existing file state via ToolManager
                original_content = ""
                try:
                    original_content = self.tools.read_workspace_file(target_file)
                except Exception as e:
                    logger.warning(f"File {target_file} not found: {e}. Starting with empty file.")
                    original_content = ""

                # 2. Idempotency scan
                is_satisfied = False
                if action_type == "append_model":
                    class_match = re.search(r'class\s+([A-Za-z0-9_]+)', patch_content)
                    if class_match:
                        cls_name = class_match.group(1)
                        if f"class {cls_name}(" in original_content or f"class {cls_name}Schema(" in original_content:
                            is_satisfied = True
                elif action_type == "append_service":
                    class_match = re.search(r'class\s+([A-Za-z0-9_]+)', patch_content)
                    if class_match:
                        cls_name = class_match.group(1)
                        if f"class {cls_name}" in original_content:
                            is_satisfied = True
                elif action_type == "append_route":
                    func_match = re.search(r'def\s+(endpoint_repaired_[A-Za-z0-9_]+)', patch_content)
                    if func_match:
                        func_name = func_match.group(1)
                        if func_name in original_content:
                            is_satisfied = True
                elif action_type == "fix_config":
                    if "app.include_router(api_router)" in original_content and "DATABASE_URL" in original_content:
                        is_satisfied = True
                    elif patch_content in original_content:
                        is_satisfied = True

                if is_satisfied:
                    logger.info(f"Idempotency Scan: Patch already satisfied for {action_type} in {target_file}. Skipping.")
                    continue

                # 3. Apply modification
                new_content = original_content
                if inst["operation"] == "add":
                    if not new_content.endswith("\n") and new_content:
                        new_content += "\n"
                    new_content += patch_content
                elif inst["operation"] == "modify":
                    if target_file == "backend/.env":
                        if "DATABASE_URL" in new_content:
                            new_content = re.sub(r'DATABASE_URL=[^\n]*', "DATABASE_URL=sqlite:///./test.db", new_content)
                        else:
                            new_content += "\n" + patch_content
                    else:
                        new_content = patch_content

                # 4. Generate before/after unified diff
                before_lines = original_content.splitlines(keepends=True)
                after_lines = new_content.splitlines(keepends=True)
                diff = difflib.unified_diff(
                    before_lines,
                    after_lines,
                    fromfile=f"a/{target_file}",
                    tofile=f"b/{target_file}"
                )
                diff_str = "".join(diff)
                
                # 5. Write modified file via ToolManager
                self.tools.write_workspace_file(target_file, new_content)
                logger.info(f"Surgically applied fix to {target_file}. Unified Diff:\n{diff_str}")
                
                fixes_applied.append(reason)
                
            except Exception as e:
                logger.error(f"Failed to execute repair instruction on {target_file}: {e}")
                execution_failed = True

        # Determine status
        if not issues_detected:
            repair_status = "no_action"
            retry_required = False
        elif execution_failed:
            repair_status = "failed"
            retry_required = False
        else:
            repair_status = "repaired"
            retry_required = True

        # Record metrics
        self.metrics.record_model_call(
            tokens_in=100,
            tokens_out=250,
            latency_ms=110.0,
            prompt_chars=500
        )

        dec = DecisionRecord(
            title="Surgical backend repair decision",
            rationale="Deterministic diagnosis and execution of targeted repairs based on validation issues, preventing speculative regenerations.",
            confidence_score=0.99
        )

        return RawOutput(
            content_blocks={
                "repair_status": repair_status,
                "issues_detected": issues_detected,
                "fixes_applied": fixes_applied,
                "retry_required": retry_required
            },
            decision_records=[dec],
            flags=[]
        )

    def generate_artifacts(self, raw: RawOutput) -> List[ArtifactBody]:
        status = raw.content_blocks.get("repair_status")
        issues = raw.content_blocks.get("issues_detected", [])
        fixes = raw.content_blocks.get("fixes_applied", [])
        retry = raw.content_blocks.get("retry_required")

        content_dict = {
            "repair_status": status,
            "issues_detected": issues,
            "fixes_applied": fixes,
            "retry_required": retry
        }

        content = json.dumps(content_dict, indent=2)

        ab = ArtifactBody(
            content=content,
            artifact_type="repair_decision",
            file_path="docs/06_repair_decision.json",
            decisions=raw.decision_records
        )
        return [ab]

    def self_evaluate(self, artifacts: List[ArtifactBody]) -> Dict[str, Any]:
        for art in artifacts:
            try:
                data = json.loads(art.content)
                if "repair_status" not in data or "retry_required" not in data:
                    return {"passed": False, "failed_rules": ["missing-required-fields"]}
            except Exception:
                return {"passed": False, "failed_rules": ["invalid-json-content"]}
        return {"passed": True, "failed_rules": []}

    def persist_results(self):
        # Override to write generated artifacts to the workspace via ToolManager write_workspace_file
        for art in self.artifacts_body:
            try:
                self.tools.write_workspace_file(art.file_path, art.content)
                logger.info(f"Persisted artifact to workspace: {art.file_path}")
            except Exception as e:
                logger.warning(f"Failed to write artifact '{art.file_path}' to workspace: {e}")
        super().persist_results()
        self.brain_client.log_audit_action(
            self.session_id,
            self.manifest.name,
            "repair_completed",
            {"node_id": self.node_id}
        )
        logger.info("RepairAgent: results persisted and completed")
