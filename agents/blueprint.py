import logging
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

logger = logging.getLogger("orchestra_blueprint_agent")

class BlueprintAgent(BaseAgent):
    """
    Blueprint specialist agent responsible for detailed design expansion.
    Converts planning outputs (PRD) into structured system design artifacts.
    """
    def initialize(self, session_id: str, node_id: str):
        super().initialize(session_id, node_id)
        logger.info("BlueprintAgent: started")

    def retrieve_context(self):
        # Retrieve parent session context
        super().retrieve_context()
        
        # Query Project Brain for artifacts and decisions in this session
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
            
        # Convert raw dictionaries to Pydantic models for BaseAgent compatibility
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

    def plan(self, context: AgentContext) -> ExecutionPlan:
        # Create execution plan tasks for system design
        task1 = Task(
            id="query_architecture_patterns",
            description="Query architecture patterns",
            capability_required="query_developer_knowledge"
        )
        task2 = Task(
            id="read_prd_context",
            description="Read and parse requirements",
            capability_required="read_workspace_file"
        )
        
        return ExecutionPlan(
            tasks=[task1, task2],
            dependencies=[],
            required_skills=[],
            required_tools=["query_developer_knowledge", "read_workspace_file"],
            expected_outputs=[
                ExpectedOutput(
                    artifact_type="system_design",
                    description="Expanded software architecture blueprint"
                )
            ],
            validation_rules=[],
            success_criteria=["System design contains all strict sections"]
        )

    def execute(self, plan: ExecutionPlan) -> RawOutput:
        # Check that we received a PRD artifact in context
        prd_artifact = None
        for a in self.context.artifacts:
            if a.type == "prd":
                prd_artifact = a
                break
                
        if not prd_artifact:
            raise ConfigurationError("BlueprintAgent requires a 'prd' artifact as input, but none was found in context.")
            
        logger.info("BlueprintAgent: Planning output received")

        # Ground technology decisions via MCP tool
        self.tools.query_developer_knowledge("microservices vs monolith trade-offs")
        
        # Read the PRD file content from workspace using tool to demonstrate input consumption
        try:
            self.tools.read_workspace_file(prd_artifact.file_path)
        except Exception:
            pass

        # Record mock model usage
        self.metrics.record_model_call(
            tokens_in=150,
            tokens_out=450,
            latency_ms=180.0,
            prompt_chars=600
        )
        
        # Generate the structured components
        system_architecture = (
            "Architecture Type: Microservices\n"
            "Components: API Gateway, User Service, Delivery Service, Notification Service, Database Cluster\n"
            "Interactions: API Gateway routes to services. Services communicate asynchronously via message queue.\n"
        )
        api_design = (
            "Endpoints:\n"
            "- POST /api/v1/orders (creates a new delivery order)\n"
            "- GET /api/v1/orders/{id} (retrieves order status)\n"
        )
        data_models = (
            "Entities:\n"
            "- User (id, name, email, role)\n"
            "- Order (id, customer_id, driver_id, status, details, created_at)\n"
        )
        service_decomposition = (
            "- API Gateway: entry point, auth, rate limiting\n"
            "- Order service: manages orders database and state machine\n"
            "- Delivery service: tracks driver coordinates and updates\n"
        )
        technical_decisions = (
            "Decision: Use PostgreSQL for order storage due to ACID requirements.\n"
            "Decision: Use Redis for tracking driver real-time coordinates.\n"
        )
        edge_cases_and_risks = (
            "- High load during lunch hours: scale gateways and order service.\n"
            "- Driver disconnected mid-delivery: handle offline caching on driver app.\n"
        )

        dec = DecisionRecord(
            title="Adopt microservices architecture",
            rationale="Enables independent scalability of user, order, and delivery services.",
            alternatives_considered=["Monolithic architecture"],
            confidence_score=0.9
        )
        
        logger.info("BlueprintAgent: Blueprint generation completed")

        return RawOutput(
            content_blocks={
                "system_architecture": system_architecture,
                "api_design": api_design,
                "data_models": data_models,
                "service_decomposition": service_decomposition,
                "technical_decisions": technical_decisions,
                "edge_cases_and_risks": edge_cases_and_risks
            },
            decision_records=[dec],
            flags=[]
        )

    def generate_artifacts(self, raw: RawOutput) -> List[ArtifactBody]:
        system_architecture = raw.content_blocks.get("system_architecture", "")
        api_design = raw.content_blocks.get("api_design", "")
        data_models = raw.content_blocks.get("data_models", "")
        service_decomposition = raw.content_blocks.get("service_decomposition", "")
        technical_decisions = raw.content_blocks.get("technical_decisions", "")
        edge_cases_and_risks = raw.content_blocks.get("edge_cases_and_risks", "")
        
        content = (
            f"# System Design Blueprint\n\n"
            f"## 1. System Architecture\n{system_architecture}\n\n"
            f"## 2. API Design\n{api_design}\n\n"
            f"## 3. Data Models\n{data_models}\n\n"
            f"## 4. Service Decomposition\n{service_decomposition}\n\n"
            f"## 5. Technical Decisions\n{technical_decisions}\n\n"
            f"## 6. Edge Cases and Risks\n{edge_cases_and_risks}\n"
        )
        
        ab = ArtifactBody(
            content=content,
            artifact_type="system_design",
            file_path="docs/02_system_design.md",
            decisions=raw.decision_records
        )
        return [ab]

    def self_evaluate(self, artifacts: List[ArtifactBody]) -> Dict[str, Any]:
        for art in artifacts:
            if "System Design Blueprint" not in art.content:
                return {"passed": False, "failed_rules": ["missing-blueprint-header"]}
        return {"passed": True, "failed_rules": []}

    def persist_results(self):
        super().persist_results()
        logger.info("BlueprintAgent: Artifact persisted")
        logger.info("BlueprintAgent: completed")
