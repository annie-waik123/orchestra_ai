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
    ExpectedOutput
)

logger = logging.getLogger("orchestra_optimization_agent")

class OptimizationAgent(BaseAgent):
    """
    OptimizationAgent is a STRICT, read-only, advisory agent.
    It analyzes the PRD, system design blueprint, backend scaffold,
    learning history, and prediction report to recommend architectural,
    structural, and maintainability improvements before runtime validation.
    """

    def initialize(self, session_id: str, node_id: str):
        super().initialize(session_id, node_id)
        logger.info("OptimizationAgent: initialized")
        self.brain_client.log_audit_action(
            self.session_id,
            self.manifest.name,
            "optimization_started",
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
        logger.info("OptimizationAgent context retrieved successfully")

    def plan(self, context: AgentContext) -> ExecutionPlan:
        task1 = Task(
            id="read_artifacts",
            description="Read PRD, System Design, Backend Scaffold, Prediction Report, and Learning History from the workspace",
            capability_required="read_workspace_file"
        )
        task2 = Task(
            id="analyze_optimizations",
            description="Perform structural analysis across 6 dimensions, compute score, and generate recommendations",
            capability_required="read_workspace_file"
        )
        return ExecutionPlan(
            tasks=[task1, task2],
            dependencies=[],
            required_skills=[],
            required_tools=["read_workspace_file"],
            expected_outputs=[
                ExpectedOutput(
                    artifact_type="optimization_report",
                    description="Advisory optimization report recommending architectural and maintainability improvements"
                )
            ],
            validation_rules=[],
            success_criteria=["Optimization report is correctly structured and contains recommendations with scoring"]
        )

    def execute(self, plan: ExecutionPlan) -> RawOutput:
        # 1. Resolve artifact paths
        prd_artifact = next((a for a in self.context.artifacts if a.type == "prd"), None)
        design_artifact = next((a for a in self.context.artifacts if a.type == "system_design"), None)
        scaffold_artifact = next((a for a in self.context.artifacts if a.type == "backend_scaffold"), None)
        learning_artifact = next((a for a in self.context.artifacts if a.type == "learning_report"), None)
        prediction_artifact = next((a for a in self.context.artifacts if a.type == "prediction_report"), None)

        prd_path = prd_artifact.file_path if prd_artifact else "docs/01_prd.md"
        design_path = design_artifact.file_path if design_artifact else "docs/02_system_design.md"
        scaffold_path = scaffold_artifact.file_path if scaffold_artifact else "docs/03_backend_scaffold.md"
        learning_path = learning_artifact.file_path if learning_artifact else "docs/07_learning_report.json"
        prediction_path = prediction_artifact.file_path if prediction_artifact else "docs/08_prediction_report.json"

        # 2. Read artifacts using ToolManager (ONLY read allowed)
        prd_content = ""
        design_content = ""
        scaffold_content = ""
        learning_content = ""
        prediction_content = ""

        # Flags for completeness and presence
        missing_prd = False
        missing_design = False
        missing_scaffold = False
        missing_learning = False
        missing_prediction = False

        incomplete_prd = False
        incomplete_design = False
        incomplete_scaffold = False
        incomplete_learning = False
        incomplete_prediction = False

        try:
            prd_content = self.tools.read_workspace_file(prd_path)
            if not prd_content.strip() or len(prd_content) < 100 or ("PRD" not in prd_content.upper() and "PRODUCT" not in prd_content.upper()):
                incomplete_prd = True
        except Exception:
            missing_prd = True

        try:
            design_content = self.tools.read_workspace_file(design_path)
            if not design_content.strip() or "## 2. API Design" not in design_content or "## 3. Data Models" not in design_content:
                incomplete_design = True
        except Exception:
            missing_design = True

        try:
            scaffold_content = self.tools.read_workspace_file(scaffold_path)
            if not scaffold_content.strip() or "backend/" not in scaffold_content:
                incomplete_scaffold = True
        except Exception:
            missing_scaffold = True

        try:
            learning_content = self.tools.read_workspace_file(learning_path)
            if learning_content:
                try:
                    json.loads(learning_content)
                except ValueError:
                    incomplete_learning = True
        except Exception:
            missing_learning = True

        try:
            prediction_content = self.tools.read_workspace_file(prediction_path)
            if prediction_content:
                try:
                    data = json.loads(prediction_content)
                    if "risk_score" not in data:
                        incomplete_prediction = True
                except ValueError:
                    incomplete_prediction = True
        except Exception:
            missing_prediction = True

        # Read actual implementation files for structural analysis (Maintainability / Configuration)
        impl_files = {
            "api": "backend/app/api.py",
            "models": "backend/app/models.py",
            "services": "backend/app/services.py",
            "config": "backend/app/config.py",
            "main": "backend/app/main.py",
            "env": "backend/.env"
        }
        impl_contents = {}
        for key, filepath in impl_files.items():
            try:
                impl_contents[key] = self.tools.read_workspace_file(filepath)
            except Exception:
                impl_contents[key] = ""

        # 3. Retrieve historical optimization/learning patterns from Project Brain
        historical_patterns = []
        if hasattr(self.brain_client, "artifacts"):
            for art in self.brain_client.artifacts.values():
                if art.get("type") in ["learning_report", "optimization_report"]:
                    try:
                        content = art.get("content", "{}")
                        if content:
                            lr_data = json.loads(content)
                            patterns = lr_data.get("failure_patterns", []) + lr_data.get("success_patterns", []) + lr_data.get("optimization_patterns", [])
                            historical_patterns.extend(patterns)
                    except Exception:
                        pass
        elif hasattr(self.brain_client, "service"):
            try:
                all_artifacts = self.brain_client.service.artifact_repo.db.read_all().values()
                for art in all_artifacts:
                    if art.get("type") in ["learning_report", "optimization_report"]:
                        content = art.get("content")
                        if content:
                            try:
                                lr_data = json.loads(content)
                                patterns = lr_data.get("failure_patterns", []) + lr_data.get("success_patterns", []) + lr_data.get("optimization_patterns", [])
                                historical_patterns.extend(patterns)
                            except Exception:
                                pass
            except Exception as e:
                logger.warning(f"Failed to query historical artifacts from BrainService: {e}")

        historical_patterns = list(set([p for p in historical_patterns if isinstance(p, str) and p.strip()]))

        # 4. Dimension-based evaluation and recommendation generation
        opportunities = []

        # -- Dimension 1: Architecture --
        # Check service count to entity count ratio
        service_defs = []
        entity_defs = []
        if design_content:
            # Extract service list and entity list
            service_defs = re.findall(r'-\s+([A-Za-z0-9_]+Service)\b', design_content)
            entity_defs = re.findall(r'-\s+([A-Za-z0-9_]+)\s*\([^)]*\)', design_content)
            # Filter entity_defs to ignore common words
            entity_defs = [e for e in entity_defs if e not in ["User", "OrderService", "Customer", "Base"]]

        # Check if single monolithic service handles multiple entities
        if len(service_defs) == 1 and len(entity_defs) >= 3:
            opportunities.append({
                "category": "architecture",
                "priority": "MEDIUM",
                "component": "services",
                "recommendation": "Decompose monolithic service into specialized entity services.",
                "reason": f"Only one service class ({service_defs[0]}) is defined to manage {len(entity_defs)} distinct domain entities. This leads to tight coupling and oversized service classes.",
                "expected_benefit": "Improves modularity, single responsibility enforcement, and service testability.",
                "confidence": 0.8
            })

        # Check coupling or dependency issues
        if "circular" in design_content.lower() or "dependent" in design_content.lower():
            opportunities.append({
                "category": "architecture",
                "priority": "LOW",
                "component": "imports",
                "recommendation": "Introduce abstraction layer (e.g. interfaces/base classes) to avoid direct dependencies.",
                "reason": "System design mentions tight class dependencies or circular relationship risks between components.",
                "expected_benefit": "Prevents circular import errors at runtime and facilitates module mocking in unit tests.",
                "confidence": 0.7
            })

        # -- Dimension 2: API Design --
        # Check versioning prefix in design or api file
        if design_content:
            endpoints = re.findall(r'-\s+(GET|POST|PUT|DELETE|PATCH)\s+([^\s]+)', design_content)
            unversioned = []
            non_rest = []
            for method, path in endpoints:
                if not path.startswith("/api/v"):
                    unversioned.append(f"{method} {path}")
                # Check REST conventions: verbs in paths like "/create_order" or "/deleteOrder"
                path_lower = path.lower()
                if any(verb in path_lower for verb in ["/create", "/delete", "/update", "/get", "/add", "/remove"]):
                    non_rest.append(f"{method} {path}")

            if unversioned:
                opportunities.append({
                    "category": "api",
                    "priority": "MEDIUM",
                    "component": "routing",
                    "recommendation": "Adopt API versioning prefixes (e.g., '/api/v1/...') for all routes.",
                    "reason": f"Endpoints like {', '.join(unversioned[:2])} lack explicit version paths.",
                    "expected_benefit": "Ensures backwards compatibility and cleaner route deprecation cycles.",
                    "confidence": 0.9
                })

            if non_rest:
                opportunities.append({
                    "category": "api",
                    "priority": "HIGH",
                    "component": "routing",
                    "recommendation": "Refactor endpoint paths to follow RESTful resource noun conventions.",
                    "reason": f"Endpoints like {', '.join(non_rest[:2])} use verbs in path routing instead of standard HTTP method verbs.",
                    "expected_benefit": "Aligns routing with REST standards and improves API readability.",
                    "confidence": 0.9
                })

        # -- Dimension 3: Data Models --
        models_code = impl_contents["models"]
        if models_code:
            # Check relationships: if there is a foreign key but no relationship defined
            # E.g. ForeignKey('customer.id') exists but relationship('Customer') is not defined
            fk_matches = re.findall(r'ForeignKey\([\'"]([a-zA-Z0-9_]+)\.', models_code)
            rel_matches = re.findall(r'relationship\([\'"]([a-zA-Z0-9_]+)[\'"]', models_code)
            missing_rels = []
            for fk in fk_matches:
                fk_camel = "".join([part.capitalize() for part in fk.split("_")])
                if fk_camel not in rel_matches and fk not in rel_matches:
                    missing_rels.append(fk)

            if missing_rels:
                opportunities.append({
                    "category": "data_models",
                    "priority": "MEDIUM",
                    "component": "database_models",
                    "recommendation": "Declare explicit SQLAlchemy ORM relationships corresponding to foreign keys.",
                    "reason": f"Foreign keys referencing tables {', '.join(set(missing_rels))} do not have matching SQLAlchemy relationship() bindings.",
                    "expected_benefit": "Enables clean object graph traversals (lazy/eager loading) and avoids manual join queries.",
                    "confidence": 0.85
                })

        # -- Dimension 4: Service Layer --
        api_code = impl_contents["api"]
        if api_code:
            # Check if API routers contain direct db queries or writes
            db_leak = False
            if re.search(r'\b(db\.query|db\.add|db\.commit|db\.execute|db\.delete)\b', api_code):
                db_leak = True

            if db_leak:
                opportunities.append({
                    "category": "services",
                    "priority": "HIGH",
                    "component": "api_routers",
                    "recommendation": "Decouple API routers from direct database logic by delegating to Service layer classes.",
                    "reason": "Direct SQLAlchemy database operations (db.query/add/commit) were detected inside api.py routes.",
                    "expected_benefit": "Enforces clean separation of concerns, simplifies routers, and enables unit testing service logic independently of HTTP context.",
                    "confidence": 0.9
                })

        # -- Dimension 5: Configuration --
        env_code = impl_contents["env"]
        config_code = impl_contents["config"]
        main_code = impl_contents["main"]

        # Check for hardcoded secrets
        hardcoded_secrets = []
        for name, code in [("config.py", config_code), ("main.py", main_code), ("api.py", api_code)]:
            if code:
                # Look for patterns like SECRET_KEY = "something" or password = "..." where it's not loaded from env
                matches = re.findall(r'\b(SECRET_KEY|PASSWORD|TOKEN|API_KEY)\s*=\s*[\'"]([^\'"]+)[\'"]', code, re.IGNORECASE)
                for key, val in matches:
                    if len(val) > 4 and not val.startswith("os.environ") and not val.startswith("getenv"):
                        hardcoded_secrets.append(f"{name}:{key}")

        if hardcoded_secrets:
            opportunities.append({
                "category": "config",
                "priority": "HIGH",
                "component": "settings",
                "recommendation": "Extract hardcoded configuration credentials and load them from environment variables.",
                "reason": f"Potential credentials found in: {', '.join(hardcoded_secrets)}.",
                "expected_benefit": "Secures credentials and prevents accidental secrets exposure in VCS commits.",
                "confidence": 0.95
            })

        # Check for environment variable validation using Pydantic Settings
        if config_code and "BaseSettings" not in config_code:
            opportunities.append({
                "category": "config",
                "priority": "MEDIUM",
                "component": "settings",
                "recommendation": "Use Pydantic BaseSettings class for structured environment configuration and type validation.",
                "reason": "Configuration loading is done using custom os.environ.get calls without centralized validation schemas.",
                "expected_benefit": "Ensures environment variable types are validated at application startup, avoiding late runtime lookup failures.",
                "confidence": 0.8
            })

        # -- Dimension 6: Maintainability --
        large_files = []
        for key, filepath in impl_files.items():
            content = impl_contents[key]
            if content:
                line_count = len(content.splitlines())
                if line_count > 300:
                    large_files.append((filepath, line_count))

        if large_files:
            opportunities.append({
                "category": "maintainability",
                "priority": "MEDIUM",
                "component": "source_files",
                "recommendation": "Split large source files into modular sub-modules or routers.",
                "reason": f"Files exceed maintainable size limits: {', '.join([f'{path} ({lines} lines)' for path, lines in large_files])}.",
                "expected_benefit": "Enhances readability, prevents merging conflicts, and structures code domains cleanly.",
                "confidence": 0.85
            })

        # 5. Apply Historical Learning Matches to increase priority/confidence
        for opp in opportunities:
            rec_text = opp["recommendation"].lower()
            reason_text = opp["reason"].lower()
            for pattern in historical_patterns:
                pat_lower = pattern.lower()
                # If historical pattern matches keywords in recommendation or reason
                if any(word in rec_text or word in reason_text for word in pat_lower.split()):
                    opp["confidence"] = min(1.0, opp["confidence"] + 0.1)
                    opp["priority"] = "HIGH"

        # 6. Deduplicate recommendations
        deduped = {}
        for opp in opportunities:
            key = (opp["category"], opp["component"], opp["recommendation"])
            if key not in deduped:
                deduped[key] = opp
            else:
                # Keep the one with higher confidence
                if opp["confidence"] > deduped[key]["confidence"]:
                    deduped[key] = opp

        optimization_opportunities = list(deduped.values())

        # 7. Scoring Algorithm
        # Base score = 10.0
        # Category penalties: HIGH = -1.5, MEDIUM = -1.0, LOW = -0.5
        # Maximum total deduction per category MUST NOT exceed 2.0
        category_penalties = {
            "architecture": 0.0,
            "api": 0.0,
            "data_models": 0.0,
            "services": 0.0,
            "config": 0.0,
            "maintainability": 0.0
        }

        for opp in optimization_opportunities:
            cat = opp["category"]
            prio = opp["priority"]
            
            penalty = 0.0
            if prio == "HIGH":
                penalty = 1.5
            elif prio == "MEDIUM":
                penalty = 1.0
            elif prio == "LOW":
                penalty = 0.5

            if cat in category_penalties:
                category_penalties[cat] += penalty

        # Apply category penalty capping
        total_deduction = 0.0
        for cat, val in category_penalties.items():
            capped_val = min(2.0, val)
            total_deduction += capped_val

        overall_score = max(0.0, min(10.0, 10.0 - total_deduction))
        overall_score = round(overall_score, 2)

        # 8. Confidence Score Calculation
        # Base confidence = 1.0
        # Deductions:
        # - Missing PRD or system_design: -0.2
        # - Missing backend_scaffold or prediction_report: -0.2
        # - No learning history available: -0.2
        # Deductions for incomplete files:
        # - Incomplete PRD/System Design/Scaffold/Learning/Prediction: -0.1 each
        confidence_deduction = 0.0
        if missing_prd or missing_design:
            confidence_deduction += 0.2
        else:
            if incomplete_prd:
                confidence_deduction += 0.1
            if incomplete_design:
                confidence_deduction += 0.1

        if missing_scaffold or missing_prediction:
            confidence_deduction += 0.2
        else:
            if incomplete_scaffold:
                confidence_deduction += 0.1
            if incomplete_prediction:
                confidence_deduction += 0.1

        # Check if local learning file is missing and no historical patterns exist in Brain
        no_learning = False
        if missing_learning and not historical_patterns:
            no_learning = True

        if no_learning:
            confidence_deduction += 0.2
        else:
            if incomplete_learning:
                confidence_deduction += 0.1

        # Additional rule: Increase confidence if historical optimization patterns match current issues
        confidence_boost = 0.0
        for opp in optimization_opportunities:
            rec_text = opp["recommendation"].lower()
            reason_text = opp["reason"].lower()
            for pattern in historical_patterns:
                pat_lower = pattern.lower()
                if any(word in rec_text or word in reason_text for word in pat_lower.split()):
                    confidence_boost += 0.05
                    break

        final_confidence = 1.0 - confidence_deduction + confidence_boost
        final_confidence = max(0.1, min(1.0, round(final_confidence, 2)))

        # 9. Classify recommendations into specialized categories
        architectural_recs = [opp for opp in optimization_opportunities if opp["category"] == "architecture"]
        maintainability_recs = [opp for opp in optimization_opportunities if opp["category"] == "maintainability"]
        
        # Performance: data models normalization/indexing, caching recommendations, etc.
        performance_recs = [
            opp for opp in optimization_opportunities 
            if opp["category"] == "data_models" or "index" in opp["recommendation"].lower() or "cache" in opp["recommendation"].lower()
        ]
        
        # Future Scalability: service decomposition, message queues, async processing
        future_scalability_recs = [
            opp for opp in optimization_opportunities 
            if "decompose" in opp["recommendation"].lower() or "scale" in opp["recommendation"].lower() or "async" in opp["recommendation"].lower()
        ]

        self.metrics.record_model_call(
            tokens_in=110,
            tokens_out=240,
            latency_ms=125.0,
            prompt_chars=550
        )

        return RawOutput(
            content_blocks={
                "overall_optimization_score": overall_score,
                "confidence": final_confidence,
                "optimization_opportunities": optimization_opportunities,
                "architectural_recommendations": architectural_recs,
                "maintainability_recommendations": maintainability_recs,
                "performance_recommendations": performance_recs,
                "future_scalability_recommendations": future_scalability_recs
            },
            decision_records=[],  # MUST NOT modify Project Brain decision logs
            flags=[]
        )

    def generate_artifacts(self, raw: RawOutput) -> List[ArtifactBody]:
        content_dict = {
            "overall_optimization_score": raw.content_blocks.get("overall_optimization_score", 10.0),
            "confidence": raw.content_blocks.get("confidence", 1.0),
            "optimization_opportunities": raw.content_blocks.get("optimization_opportunities", []),
            "architectural_recommendations": raw.content_blocks.get("architectural_recommendations", []),
            "maintainability_recommendations": raw.content_blocks.get("maintainability_recommendations", []),
            "performance_recommendations": raw.content_blocks.get("performance_recommendations", []),
            "future_scalability_recommendations": raw.content_blocks.get("future_scalability_recommendations", [])
        }
        content = json.dumps(content_dict, indent=2)
        ab = ArtifactBody(
            content=content,
            artifact_type="optimization_report",
            file_path="docs/09_optimization_report.json",
            decisions=[]  # Advisory only, no decisions logged
        )
        return [ab]

    def self_evaluate(self, artifacts: List[ArtifactBody]) -> Dict[str, Any]:
        for art in artifacts:
            try:
                data = json.loads(art.content)
                required_fields = [
                    "overall_optimization_score", "confidence", "optimization_opportunities",
                    "architectural_recommendations", "maintainability_recommendations",
                    "performance_recommendations", "future_scalability_recommendations"
                ]
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
                logger.info(f"Persisted optimization report to workspace: {art.file_path}")
            except Exception as e:
                logger.warning(f"Failed to write optimization report '{art.file_path}' to workspace: {e}")
        
        # Save in Brain database (which does not affect runtime state or create decisions)
        super().persist_results()
        
        self.brain_client.log_audit_action(
            self.session_id,
            self.manifest.name,
            "optimization_completed",
            {"node_id": self.node_id}
        )
        logger.info("OptimizationAgent: results persisted and completed")
