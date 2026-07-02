import logging
import re
import json
import hashlib
from typing import List, Dict, Any

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

logger = logging.getLogger("orchestra_evaluation_agent")

class EvaluationAgent(BaseAgent):
    """
    EvaluationAgent is a STRICT, deterministic, read-only evaluator.
    It evaluates the full engineering pipeline quality using existing artifacts.
    It MUST NOT generate code, execute code, or modify artifacts.
    """

    def initialize(self, session_id: str, node_id: str):
        super().initialize(session_id, node_id)
        logger.info("EvaluationAgent: initialized")
        self.brain_client.log_audit_action(
            self.session_id,
            self.manifest.name,
            "evaluation_started",
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
        logger.info("EvaluationAgent context retrieved successfully")

    def plan(self, context: AgentContext) -> ExecutionPlan:
        task1 = Task(
            id="read_pipeline_artifacts",
            description="Read PRD, System Design, Backend Scaffold, and Execution Report artifacts from the workspace",
            capability_required="read_workspace_file"
        )
        task2 = Task(
            id="evaluate_pipeline",
            description="Perform deterministic architecture, completeness, runtime, and pipeline checks",
            capability_required="read_workspace_file"
        )
        return ExecutionPlan(
            tasks=[task1, task2],
            dependencies=[],
            required_skills=[],
            required_tools=["read_workspace_file"],
            expected_outputs=[
                ExpectedOutput(
                    artifact_type="evaluation_report",
                    description="Deterministic pipeline evaluation report"
                )
            ],
            validation_rules=[],
            success_criteria=["Evaluation report is correctly structured and scored"]
        )

    def execute(self, plan: ExecutionPlan) -> RawOutput:
        # Collect artifacts metadata from context
        prd_artifact = next((a for a in self.context.artifacts if a.type == "prd"), None)
        blueprint_artifact = next((a for a in self.context.artifacts if a.type == "system_design"), None)
        scaffold_artifact = next((a for a in self.context.artifacts if a.type == "backend_scaffold"), None)
        validation_artifact = next((a for a in self.context.artifacts if a.type == "execution_report"), None)

        issues = []
        recommendations = []

        # 1. Pipeline Completeness & Lineage (max 2.0 points)
        pipeline_score = 0.0
        all_artifacts_present = True

        # Check artifact presence
        for name, art, weight in [("PRD", prd_artifact, 0.25), 
                                  ("System Design Blueprint", blueprint_artifact, 0.25), 
                                  ("Backend Scaffold Summary", scaffold_artifact, 0.25), 
                                  ("Execution Report", validation_artifact, 0.25)]:
            if art:
                pipeline_score += weight
            else:
                all_artifacts_present = False
                issues.append(f"Missing {name} artifact from pipeline.")
                recommendations.append(f"Ensure the workflow completes the {name} generation step.")

        # Check lineage
        lineage_ok = True
        if blueprint_artifact:
            # Blueprint depends on PRD
            prd_path = prd_artifact.file_path if prd_artifact else "docs/01_prd.md"
            if prd_path not in blueprint_artifact.depends_on:
                lineage_ok = False
                issues.append("Lineage breach: System Design Blueprint does not depend on PRD.")
                recommendations.append("Configure BlueprintAgent outputs to declare dependency on PRD.")
            else:
                pipeline_score += 0.33
        else:
            lineage_ok = False

        if scaffold_artifact:
            # Scaffold depends on Blueprint
            blueprint_path = blueprint_artifact.file_path if blueprint_artifact else "docs/02_system_design.md"
            if blueprint_path not in scaffold_artifact.depends_on:
                lineage_ok = False
                issues.append("Lineage breach: Backend Scaffold does not depend on System Design Blueprint.")
                recommendations.append("Configure ImplementationAgent outputs to declare dependency on System Design Blueprint.")
            else:
                pipeline_score += 0.33
        else:
            lineage_ok = False

        if validation_artifact:
            # Validation depends on Scaffold
            scaffold_path = scaffold_artifact.file_path if scaffold_artifact else "docs/03_backend_scaffold.md"
            if scaffold_path not in validation_artifact.depends_on:
                lineage_ok = False
                issues.append("Lineage breach: Execution Report does not depend on Backend Scaffold.")
                recommendations.append("Configure RuntimeValidationAgent outputs to declare dependency on Backend Scaffold.")
            else:
                pipeline_score += 0.34
        else:
            lineage_ok = False

        pipeline_score = round(min(pipeline_score, 2.0), 2)

        # 2. Runtime Evidence (max 2.0 points)
        runtime_score = 0.0
        runtime_success = False
        if validation_artifact:
            try:
                report_content = self.tools.read_workspace_file(validation_artifact.file_path)
                
                # Check execution success
                success_match = "SUCCESS" in report_content or "**Status**: SUCCESS" in report_content
                if success_match:
                    runtime_success = True
                    runtime_score += 0.5
                else:
                    issues.append("Runtime validation did not report SUCCESS status.")
                    recommendations.append("Investigate sandbox run failures and fix backend errors.")

                # Check config load success
                config_match = "Configuration Loaded: PASSED" in report_content
                if config_match:
                    runtime_score += 0.5
                else:
                    issues.append("Configuration failed to load in sandbox.")
                    recommendations.append("Check database URLs, environment variables, and config.py setup.")

                # Check import success
                import_match = "Python Imports Valid: PASSED" in report_content
                if import_match:
                    runtime_score += 0.5
                else:
                    issues.append("Python imports failed in generated code.")
                    recommendations.append("Check for circular imports or missing modules in backend/app/main.py.")

                # Check route discovery success
                routes_match = "Routes Loaded: PASSED" in report_content or "FastAPI App Initialized: PASSED" in report_content
                if routes_match:
                    runtime_score += 0.5
                else:
                    issues.append("No API routes discovered during sandbox execution.")
                    recommendations.append("Register API routers properly under the FastAPI app object.")
            except Exception as e:
                issues.append(f"Could not read execution report: {e}")
                recommendations.append("Verify filesystem MCP permissions and execution report file existence.")
        else:
            issues.append("Execution report is missing from the workspace.")
            recommendations.append("Run the validation step to produce runtime validation evidence.")

        runtime_score = round(runtime_score, 2)

        # 3. Architecture Consistency (3.0 max) & 4. Implementation Completeness (3.0 max)
        arch_score = 0.0
        impl_score = 0.0

        if blueprint_artifact:
            blueprint_content = ""
            try:
                blueprint_content = self.tools.read_workspace_file(blueprint_artifact.file_path)
            except Exception as e:
                issues.append(f"Failed to read System Design Blueprint: {e}")
                recommendations.append("Verify Blueprint file is generated at the correct location.")

            if blueprint_content:
                # Parse structured blueprint specifications
                blueprint_specs = self._parse_blueprint(blueprint_content)
                endpoints = blueprint_specs.get("endpoints", [])
                entities = blueprint_specs.get("entities", [])
                services = blueprint_specs.get("services", [])

                # Verify files presence for Architecture Consistency Structure Match
                # Read implementation files if they exist
                api_code = ""
                models_code = ""
                services_code = ""
                
                scaffold_files = []
                if scaffold_artifact:
                    try:
                        scaffold_content = self.tools.read_workspace_file(scaffold_artifact.file_path)
                        # Extract list of files under ## Generated File Structure
                        match = re.search(r'## Generated File Structure\s*([\s\S]*?)(?:\n##|$)', scaffold_content)
                        if match:
                            for line in match.group(1).splitlines():
                                line_stripped = line.strip()
                                if line_stripped.startswith("-") or line_stripped.startswith("*"):
                                    fpath = line_stripped.lstrip("-* ").strip()
                                    if fpath:
                                        scaffold_files.append(fpath)
                    except Exception:
                        pass
                
                if not scaffold_files:
                    scaffold_files = [
                        "backend/.env", "backend/app/config.py", "backend/app/db.py",
                        "backend/app/models.py", "backend/app/services.py",
                        "backend/app/api.py", "backend/app/main.py"
                    ]

                present_files_count = 0
                for fpath in scaffold_files:
                    try:
                        f_content = self.tools.read_workspace_file(fpath)
                        present_files_count += 1
                        if fpath == "backend/app/api.py":
                            api_code = f_content
                        elif fpath == "backend/app/models.py":
                            models_code = f_content
                        elif fpath == "backend/app/services.py":
                            services_code = f_content
                    except Exception:
                        issues.append(f"Scaffold file '{fpath}' is missing or unreadable.")
                        recommendations.append(f"Re-run implementation agent to write {fpath}.")

                # Structure match score (max 1.0)
                if scaffold_files:
                    arch_score += (present_files_count / len(scaffold_files)) * 1.0

                # Check endpoints (Implementation Completeness & Consistency)
                total_endpoints = len(endpoints)
                matched_endpoints = 0
                for endp in endpoints:
                    match = re.search(r'(GET|POST|PUT|DELETE|PATCH)\s+([^\s(]+)', endp, re.IGNORECASE)
                    if match:
                        method = match.group(1).lower()
                        path = match.group(2)
                        
                        # Match decorator patterns
                        pattern1 = f"@router.{method}('{path}')"
                        pattern2 = f'@router.{method}("{path}")'
                        pattern3 = f"@app.{method}('{path}')"
                        pattern4 = f'@app.{method}("{path}")'
                        
                        if (pattern1 in api_code or pattern2 in api_code or 
                            pattern3 in api_code or pattern4 in api_code):
                            matched_endpoints += 1
                        else:
                            issues.append(f"Missing API endpoint {method.upper()} {path} in api.py.")
                            recommendations.append(f"Implement route {method.upper()} {path} under APIRouter in api.py.")
                    else:
                        total_endpoints -= 1 # Ignore unparseable designs

                endpoint_completeness = (matched_endpoints / total_endpoints) if total_endpoints > 0 else 1.0
                impl_score += endpoint_completeness * 1.0

                # Check entities / models (Implementation Completeness & Consistency)
                total_entities = len(entities)
                matched_entities = 0
                for ent in entities:
                    match = re.match(r'^([A-Za-z0-9_]+)', ent)
                    if match:
                        ent_name = match.group(1)
                        class_pat1 = f"class {ent_name}(Base):"
                        class_pat2 = f"class {ent_name}Schema(BaseModel):"
                        
                        if class_pat1 in models_code or class_pat2 in models_code:
                            matched_entities += 1
                        else:
                            issues.append(f"Missing Entity class/schema for '{ent_name}' in models.py.")
                            recommendations.append(f"Declare class {ent_name}(Base) in backend/app/models.py.")
                    else:
                        total_entities -= 1

                entity_completeness = (matched_entities / total_entities) if total_entities > 0 else 1.0
                impl_score += entity_completeness * 1.0
                arch_score += entity_completeness * 1.0 # Component Presence (max 1.0)

                # Check services (Implementation Completeness & Consistency)
                total_services = len(services)
                matched_services = 0
                for svc in services:
                    svc_name = svc.split(":")[0].strip()
                    svc_name = re.sub(r'[^A-Za-z0-9_]', '', svc_name)
                    if svc_name:
                        class_pat = f"class {svc_name}:"
                        class_pat_paren = f"class {svc_name}("
                        if class_pat in services_code or class_pat_paren in services_code:
                            matched_services += 1
                        else:
                            issues.append(f"Missing Service class '{svc_name}' in services.py.")
                            recommendations.append(f"Declare class {svc_name} in backend/app/services.py.")
                    else:
                        total_services -= 1

                service_completeness = (matched_services / total_services) if total_services > 0 else 1.0
                impl_score += service_completeness * 1.0
                arch_score += service_completeness * 1.0 # Service structure alignment (max 1.0)
        else:
            issues.append("Blueprint artifact is missing. Cannot verify architecture or implementation details.")
            recommendations.append("Ensure the Blueprint step completes successfully before running evaluation.")

        arch_score = round(min(arch_score, 3.0), 2)
        impl_score = round(min(impl_score, 3.0), 2)

        # Composite score calculation (max 10.0)
        composite_score = round(arch_score + impl_score + runtime_score + pipeline_score, 2)

        # Status logic
        if all_artifacts_present and runtime_success and composite_score >= 8.5:
            status = "PASS"
        elif composite_score < 5.0 or not runtime_success or not all_artifacts_present:
            status = "FAIL"
        else:
            status = "PARTIAL"

        dec = DecisionRecord(
            title="Pipeline execution quality evaluation gate",
            rationale="Determines pipeline quality and verification scores strictly from collected verification artifacts and metadata.",
            alternatives_considered=[],
            confidence_score=1.0
        )

        self.metrics.record_model_call(
            tokens_in=100,
            tokens_out=200,
            latency_ms=100.0,
            prompt_chars=500
        )

        return RawOutput(
            content_blocks={
                "score": composite_score,
                "status": status,
                "breakdown": {
                    "architecture_consistency": arch_score,
                    "implementation_completeness": impl_score,
                    "runtime_evidence": runtime_score,
                    "pipeline_completeness": pipeline_score
                },
                "issues": list(set(issues)),
                "recommendations": list(set(recommendations))
            },
            decision_records=[dec],
            flags=[]
        )

    def generate_artifacts(self, raw: RawOutput) -> List[ArtifactBody]:
        score = raw.content_blocks.get("score")
        status = raw.content_blocks.get("status")
        bd = raw.content_blocks.get("breakdown", {})
        issues = raw.content_blocks.get("issues", [])
        recs = raw.content_blocks.get("recommendations", [])

        issues_str = "\n".join([f"- {i}" for i in issues]) if issues else "None"
        recs_str = "\n".join([f"- {r}" for r in recs]) if recs else "None"

        content = (
            f"# Evaluation Report\n\n"
            f"## 1. Summary\n"
            f"- **Overall Score**: {score}/10.0\n"
            f"- **Status**: {status}\n"
            f"- **Summary**: Pipeline validation completed with status {status} and score {score}.\n\n"
            f"## 2. Individual Check Results\n"
            f"- **Architecture Consistency**: {bd.get('architecture_consistency')}/3.0\n"
            f"- **Implementation Completeness**: {bd.get('implementation_completeness')}/3.0\n"
            f"- **Runtime Evidence**: {bd.get('runtime_evidence')}/2.0\n"
            f"- **Pipeline Completeness & Lineage**: {bd.get('pipeline_completeness')}/2.0\n"
            f"- **Security Check**: NOT_EVALUATED\n\n"
            f"## 3. Issues Detected\n"
            f"{issues_str}\n\n"
            f"## 4. Recommendations\n"
            f"{recs_str}\n"
        )

        ab = ArtifactBody(
            content=content,
            artifact_type="evaluation_report",
            file_path="docs/05_evaluation_report.md",
            decisions=raw.decision_records
        )
        return [ab]

    def self_evaluate(self, artifacts: List[ArtifactBody]) -> Dict[str, Any]:
        for art in artifacts:
            if "Evaluation Report" not in art.content:
                return {"passed": False, "failed_rules": ["missing-evaluation-report-header"]}
        return {"passed": True, "failed_rules": []}

    def _parse_blueprint(self, content: str) -> Dict[str, List[str]]:
        """Extract structured sections from system design blueprint."""
        import json
        try:
            data = json.loads(content)
            return {
                "endpoints": data.get("api_design", {}).get("endpoints", []),
                "entities": data.get("data_models", {}).get("entities", []),
                "services": data.get("service_decomposition", {}).get("services", [])
            }
        except json.JSONDecodeError:
            pass

        sections = {
            "endpoints": [],
            "entities": [],
            "services": []
        }
        
        current_section = None
        for line in content.splitlines():
            line_stripped = line.strip()
            if not line_stripped:
                continue
            if "## 2. API Design" in line_stripped:
                current_section = "endpoints"
            elif "## 3. Data Models" in line_stripped:
                current_section = "entities"
            elif "## 4. Service Decomposition" in line_stripped:
                current_section = "services"
            elif line_stripped.startswith("## "):
                current_section = None
            elif current_section and (line_stripped.startswith("-") or line_stripped.startswith("*")):
                item = line_stripped.lstrip("-* ").strip()
                if item:
                    sections[current_section].append(item)
                    
        return sections
