import json
import logging
import re
from typing import List, Dict, Any, Optional

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

logger = logging.getLogger("orchestra_predictive_agent")

class PredictiveAgent(BaseAgent):
    """
    PredictiveAgent is a STRICT, read-only, advisory agent.
    It analyzes the system design blueprint and historical learning reports
    to predict potential runtime failures and assign normalized risk scores.
    """

    def initialize(self, session_id: str, node_id: str):
        super().initialize(session_id, node_id)
        logger.info("PredictiveAgent: initialized")
        self.brain_client.log_audit_action(
            self.session_id,
            self.manifest.name,
            "prediction_started",
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
        logger.info("PredictiveAgent context retrieved successfully")

    def plan(self, context: AgentContext) -> ExecutionPlan:
        task1 = Task(
            id="read_design_and_learning",
            description="Read PRD, System Design, and Learning Report artifacts from the workspace",
            capability_required="read_workspace_file"
        )
        task2 = Task(
            id="analyze_risks",
            description="Extract blueprint components and compare against implementation state to predict failures",
            capability_required="read_workspace_file"
        )
        return ExecutionPlan(
            tasks=[task1, task2],
            dependencies=[],
            required_skills=[],
            required_tools=["read_workspace_file"],
            expected_outputs=[
                ExpectedOutput(
                    artifact_type="prediction_report",
                    description="Advisory prediction report mapping system design risks"
                )
            ],
            validation_rules=[],
            success_criteria=["Prediction report is correctly structured and contains risk scoring"]
        )

    def parse_system_design(self, content: str) -> Dict[str, Any]:
        """
        Extract structured sections from BlueprintAgent output.
        First tries to parse content as JSON. Fallback to markdown section parsing.
        """
        try:
            data = json.loads(content)
            return {
                "endpoints": data.get("api_design", {}).get("endpoints", []),
                "entities": data.get("data_models", {}).get("entities", []),
                "services": data.get("service_decomposition", {}).get("services", []),
                "config": data.get("configuration", {}).get("variables", ["ENV", "DATABASE_URL", "HOST", "PORT"])
            }
        except json.JSONDecodeError:
            pass

        # Parse markdown using header triggers
        sections = {
            "endpoints": [],
            "entities": [],
            "services": [],
            "config": []
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
            elif "## 5. Configuration" in line_stripped or "## Configuration" in line_stripped:
                current_section = "config"
            elif line_stripped.startswith("## "):
                current_section = None
            elif current_section and (line_stripped.startswith("-") or line_stripped.startswith("*")):
                item = line_stripped.lstrip("-* ").strip()
                if item:
                    sections[current_section].append(item)
                    
        # If no config variables were found in the config section, look for standard ones anywhere,
        # or fallback to defaults
        if not sections["config"]:
            found_vars = set(re.findall(r'\b(DATABASE_URL|ENV|HOST|PORT|SECRET_KEY)\b', content))
            if found_vars:
                sections["config"] = list(found_vars)
            else:
                sections["config"] = ["ENV", "DATABASE_URL", "HOST", "PORT"]

        return sections

    def execute(self, plan: ExecutionPlan) -> RawOutput:
        # 1. Resolve artifact paths
        blueprint_artifact = next((a for a in self.context.artifacts if a.type == "system_design"), None)
        learning_artifact = next((a for a in self.context.artifacts if a.type == "learning_report"), None)

        blueprint_path = blueprint_artifact.file_path if blueprint_artifact else "docs/02_system_design.md"
        learning_path = learning_artifact.file_path if learning_artifact else "docs/07_learning_report.json"

        # 2. Read artifacts using ToolManager (ONLY read allowed)
        blueprint_content = ""
        learning_content = ""
        warnings = []
        confidence = 1.0

        try:
            blueprint_content = self.tools.read_workspace_file(blueprint_path)
            logger.info(f"Read blueprint from {blueprint_path}")
        except Exception as e:
            logger.warning(f"Could not read blueprint file: {e}")
            warnings.append(f"Blueprint file '{blueprint_path}' not found.")
            confidence -= 0.2

        try:
            learning_content = self.tools.read_workspace_file(learning_path)
            logger.info(f"Read learning report from {learning_path}")
        except Exception as e:
            logger.info(f"Learning report file not found: {e}")
            # Treat missing learning report as a signal, not a fatal error
            warnings.append("Local learning report (docs/07_learning_report.json) not found.")
            confidence -= 0.25

        # 3. Parse system design components
        specs = self.parse_system_design(blueprint_content)
        endpoints = specs.get("endpoints", [])
        entities = specs.get("entities", [])
        services = specs.get("services", [])
        config_vars = specs.get("config", [])

        # 4. Check actual implementation state
        impl_files = {
            "api": "backend/app/api.py",
            "database": "backend/app/models.py",
            "services": "backend/app/services.py",
            "config": "backend/.env"
        }

        impl_contents = {}
        for key, path in impl_files.items():
            try:
                content = self.tools.read_workspace_file(path)
                impl_contents[key] = content
            except Exception:
                # Treat missing implementation file as a signal, not an error
                impl_contents[key] = None
                warnings.append(f"Implementation file '{path}' is missing.")

        # 5. Extract failure patterns from learning history and Project Brain
        failure_patterns = []

        # Current session's learning report
        if learning_content:
            try:
                lr_data = json.loads(learning_content)
                failure_patterns.extend(lr_data.get("failure_patterns", []))
            except Exception as e:
                logger.warning(f"Failed to parse learning report JSON: {e}")

        # Historical failure patterns from Project Brain across all sessions
        historical_count = 0
        if hasattr(self.brain_client, "artifacts"):
            # Mock client
            for art in self.brain_client.artifacts.values():
                if art.get("type") == "learning_report":
                    try:
                        lr_data = json.loads(art.get("content", "{}"))
                        failure_patterns.extend(lr_data.get("failure_patterns", []))
                        historical_count += 1
                    except Exception:
                        pass
        elif hasattr(self.brain_client, "service"):
            # Local client
            try:
                all_artifacts = self.brain_client.service.artifact_repo.db.read_all().values()
                for art in all_artifacts:
                    if art.get("type") == "learning_report":
                        try:
                            content = art.get("content")
                            if content:
                                lr_data = json.loads(content)
                                failure_patterns.extend(lr_data.get("failure_patterns", []))
                                historical_count += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Failed to query historical artifacts from BrainService: {e}")

        if historical_count == 0:
            confidence -= 0.25

        # Limit confidence bounds
        confidence = max(0.1, min(1.0, confidence))

        # Remove duplicate failure patterns
        failure_patterns = list(set(failure_patterns))

        # 6. Analyze mismatches and calculate risk scores
        missing_endpoints = []
        missing_entities = []
        missing_services = []
        missing_configs = []

        # API check
        api_content = impl_contents["api"]
        if api_content is None:
            missing_endpoints = endpoints.copy()
        else:
            for endp in endpoints:
                # Find HTTP method and path e.g. "POST /api/v1/orders"
                match = re.search(r'(GET|POST|PUT|DELETE|PATCH)\s+([^\s(]+)', endp, re.IGNORECASE)
                if match:
                    method = match.group(1).lower()
                    path = match.group(2)
                    # Check for combinations of method and path in the file, ignoring quotes
                    pattern = rf"\.{method}\s*\(\s*['\"]{re.escape(path)}['\"]"
                    if not re.search(pattern, api_content, re.IGNORECASE):
                        missing_endpoints.append(endp)
                else:
                    if endp not in api_content:
                        missing_endpoints.append(endp)

        # Database check
        models_content = impl_contents["database"]
        if models_content is None:
            missing_entities = entities.copy()
        else:
            for ent in entities:
                # Entity name e.g. "User (id, name, email)" -> "User"
                name_match = re.match(r'^([A-Za-z0-9_]+)', ent)
                if name_match:
                    name = name_match.group(1)
                    if f"class {name}" not in models_content:
                        missing_entities.append(ent)
                else:
                    if ent not in models_content:
                        missing_entities.append(ent)

        # Services check
        services_content = impl_contents["services"]
        if services_content is None:
            missing_services = services.copy()
        else:
            for svc in services:
                # Split on space, colon, or open parenthesis to find first word
                svc_name = re.split(r'[:\s(]', svc)[0].strip()
                svc_name = re.sub(r'[^A-Za-z0-9_]', '', svc_name)
                if svc_name and f"class {svc_name}" not in services_content:
                    missing_services.append(svc)

        # Config check
        env_content = impl_contents["config"]
        if env_content is None:
            missing_configs = config_vars.copy()
        else:
            for cvar in config_vars:
                cvar_stripped = cvar.strip()
                if cvar_stripped and f"{cvar_stripped}=" not in env_content:
                    missing_configs.append(cvar)

        # Base category scores (normalized to 0-10)
        # If the file is completely missing, the score is automatically 10.0 (high-risk signal).
        api_base = 10.0 if impl_contents["api"] is None else ((len(missing_endpoints) / len(endpoints) * 10.0) if endpoints else 0.0)
        db_base = 10.0 if impl_contents["database"] is None else ((len(missing_entities) / len(entities) * 10.0) if entities else 0.0)
        svc_base = 10.0 if impl_contents["services"] is None else ((len(missing_services) / len(services) * 10.0) if services else 0.0)
        cfg_base = 10.0 if impl_contents["config"] is None else ((len(missing_configs) / len(config_vars) * 10.0) if config_vars else 0.0)

        # Apply Multiplicative Influence from matched failure patterns
        api_multiplier = 1.0
        db_multiplier = 1.0
        svc_multiplier = 1.0
        cfg_multiplier = 1.0
        system_multiplier = 1.0

        for pattern in failure_patterns:
            pattern_lower = pattern.lower()
            if "endpoint" in pattern_lower or "route" in pattern_lower or "api" in pattern_lower:
                api_multiplier *= 1.5
            if "database" in pattern_lower or "entity" in pattern_lower or "model" in pattern_lower or "schema" in pattern_lower:
                db_multiplier *= 1.5
            if "service" in pattern_lower or "logic" in pattern_lower:
                svc_multiplier *= 1.5
            if "config" in pattern_lower or "env" in pattern_lower or "environment" in pattern_lower:
                cfg_multiplier *= 1.5
            if "import" in pattern_lower or "circular" in pattern_lower:
                system_multiplier *= 1.5

        # Final category scores (normalized, capped at 10.0)
        api_risk = min(10.0, api_base * api_multiplier)
        db_risk = min(10.0, db_base * db_multiplier)
        svc_risk = min(10.0, svc_base * svc_multiplier)
        cfg_risk = min(10.0, cfg_base * cfg_multiplier)

        # Generate warnings and failure predictions
        failure_predictions = []
        preventive_recommendations = []

        if missing_endpoints:
            for endp in missing_endpoints:
                failure_predictions.append({
                    "component": "api",
                    "failure_type": "missing_endpoint",
                    "description": f"Endpoint '{endp}' defined in blueprint is not found in api.py",
                    "severity": "HIGH"
                })
                preventive_recommendations.append(f"Implement missing API endpoint '{endp}' in backend/app/api.py")

        if missing_entities:
            for ent in missing_entities:
                failure_predictions.append({
                    "component": "database",
                    "failure_type": "missing_entity",
                    "description": f"Data model entity '{ent}' defined in blueprint is not found in models.py",
                    "severity": "HIGH"
                })
                preventive_recommendations.append(f"Implement database entity model class for '{ent}' in backend/app/models.py")

        if missing_services:
            for svc in missing_services:
                failure_predictions.append({
                    "component": "services",
                    "failure_type": "missing_service",
                    "description": f"Service layer stub '{svc}' defined in blueprint is not found in services.py",
                    "severity": "HIGH"
                })
                preventive_recommendations.append(f"Implement business logic class for service '{svc}' in backend/app/services.py")

        if missing_configs:
            for cvar in missing_configs:
                failure_predictions.append({
                    "component": "config",
                    "failure_type": "missing_config",
                    "description": f"Environment variable '{cvar}' defined in blueprint is not found in .env",
                    "severity": "HIGH"
                })
                preventive_recommendations.append(f"Define environment variable '{cvar}' in backend/.env")

        # Map high risk components
        high_risk_components = []
        components_map = {
            "api": (api_risk, "API routing components missing or matching historical failure patterns."),
            "database": (db_risk, "Database schema/entities missing or matching historical failure patterns."),
            "services": (svc_risk, "Business logic services missing or matching historical failure patterns."),
            "config": (cfg_risk, "Environment configurations missing or matching historical failure patterns.")
        }
        for name, (score, reason) in components_map.items():
            if score >= 5.0:
                high_risk_components.append({
                    "name": name,
                    "risk_score": round(score, 2),
                    "reason": reason
                })

        # Calculate overall risk score
        overall_base = (api_risk + db_risk + svc_risk + cfg_risk) / 4.0
        overall_risk = min(10.0, overall_base * system_multiplier)

        # Recommendations based on historical failure pattern matches
        for pattern in failure_patterns:
            pattern_lower = pattern.lower()
            if "database" in pattern_lower and missing_entities:
                rec = "Pre-declare all database entities and models in the system design blueprint to prevent repair loops."
                if rec not in preventive_recommendations:
                    preventive_recommendations.append(rec)
            if "endpoint" in pattern_lower and missing_endpoints:
                rec = "Ensure all design routes are completely mapped and implemented in the router layer."
                if rec not in preventive_recommendations:
                    preventive_recommendations.append(rec)
            if "config" in pattern_lower and missing_configs:
                rec = "Configure all required environment variables in backend/.env prior to validation stage."
                if rec not in preventive_recommendations:
                    preventive_recommendations.append(rec)

        if not preventive_recommendations:
            preventive_recommendations.append("Maintain consistent design and schema definitions between Blueprint and Implementation phases.")

        # Record mock model call metrics
        self.metrics.record_model_call(
            tokens_in=95,
            tokens_out=210,
            latency_ms=110.0,
            prompt_chars=480
        )

        return RawOutput(
            content_blocks={
                "risk_score": round(overall_risk, 2),
                "confidence": round(confidence, 2),
                "high_risk_components": high_risk_components,
                "warnings": warnings,
                "failure_predictions": failure_predictions,
                "preventive_recommendations": preventive_recommendations
            },
            decision_records=[],  # MUST NOT modify Project Brain decision logs
            flags=[]
        )

    def generate_artifacts(self, raw: RawOutput) -> List[ArtifactBody]:
        content_dict = {
            "risk_score": raw.content_blocks.get("risk_score", 0.0),
            "confidence": raw.content_blocks.get("confidence", 1.0),
            "high_risk_components": raw.content_blocks.get("high_risk_components", []),
            "warnings": raw.content_blocks.get("warnings", []),
            "failure_predictions": raw.content_blocks.get("failure_predictions", []),
            "preventive_recommendations": raw.content_blocks.get("preventive_recommendations", [])
        }
        content = json.dumps(content_dict, indent=2)
        ab = ArtifactBody(
            content=content,
            artifact_type="prediction_report",
            file_path="docs/08_prediction_report.json",
            decisions=[]  # Crucial: NO decisions logged to Project Brain
        )
        return [ab]

    def self_evaluate(self, artifacts: List[ArtifactBody]) -> Dict[str, Any]:
        for art in artifacts:
            try:
                data = json.loads(art.content)
                required_fields = ["risk_score", "confidence", "high_risk_components", "warnings", "failure_predictions", "preventive_recommendations"]
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
                logger.info(f"Persisted prediction report to workspace: {art.file_path}")
            except Exception as e:
                logger.warning(f"Failed to write prediction report '{art.file_path}' to workspace: {e}")
        
        # Save in Brain database (which does not affect runtime state or create decisions)
        super().persist_results()
        
        self.brain_client.log_audit_action(
            self.session_id,
            self.manifest.name,
            "prediction_completed",
            {"node_id": self.node_id}
        )
        logger.info("PredictiveAgent: results persisted and completed")
