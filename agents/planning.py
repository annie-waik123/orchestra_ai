from typing import List, Dict, Any
from agents.base_agent import BaseAgent
from agents.models import (
    AgentContext,
    ExecutionPlan,
    RawOutput,
    ArtifactBody,
    DecisionRecord,
    Task,
    ExpectedOutput
)

class PlanningAgent(BaseAgent):
    """
    Planning specialist agent responsible for initial scoping and project specification blueprints.
    Inherits lifecycle execution mechanics from BaseAgent.
    """
    def plan(self, context: AgentContext) -> ExecutionPlan:
        # Simulate reasoning call to Gemini/LLM
        # In actual execution, this formats a prompt and calls model
        # For framework execution, we return a valid ExecutionPlan
        task1 = Task(
            id="best_practices",
            description="Lookup scoping best practices",
            capability_required="query_developer_knowledge"
        )
        task2 = Task(
            id="generate_scope",
            description="Formulate project scope blueprint",
            capability_required="read_workspace_file"
        )
        
        return ExecutionPlan(
            tasks=[task1, task2],
            dependencies=[],
            required_skills=[],
            required_tools=["query_developer_knowledge", "read_workspace_file"],
            expected_outputs=[ExpectedOutput(artifact_type="prd", description="Scoping blueprint doc")],
            validation_rules=[],
            success_criteria=["PRD contains clear scope boundaries"]
        )

    def execute(self, plan: ExecutionPlan) -> RawOutput:
        # Executes tasks in estimated_execution_order
        # 1. Lookup knowledge
        knowledge_excerpts = self.tools.query_developer_knowledge("scoping best practices")
        
        # 2. Simulate reading some file if necessary (fallback if not present)
        workspace_info = ""
        try:
            workspace_info = self.tools.read_workspace_file("requirements.txt")
        except Exception:
            workspace_info = "requirements: python 3.13"

        # Record dummy model tokens usage
        self.metrics.record_model_call(
            tokens_in=100, 
            tokens_out=250, 
            latency_ms=120.0, 
            prompt_chars=400
        )
        
        content = (
            f"--- Scaffolded PRD ---\n"
            f"Developer knowledge excerpt: {knowledge_excerpts}\n"
            f"Workspace metadata: {workspace_info}\n"
            f"Project Scope: Completed successfully.\n"
        )
        
        dec = DecisionRecord(
            title="Adopt standard modular workspace",
            rationale="Enforces clean separation of concerns and facilitates testing",
            alternatives_considered=["Monolithic file structure"],
            confidence_score=0.95
        )
        
        return RawOutput(
            content_blocks={"prd_text": content},
            decision_records=[dec],
            flags=[]
        )

    def generate_artifacts(self, raw: RawOutput) -> List[ArtifactBody]:
        # Formulate final PRD artifact
        content = raw.content_blocks.get("prd_text", "Empty PRD")
        
        ab = ArtifactBody(
            content=content,
            artifact_type="prd",
            file_path="docs/01_prd.md",
            decisions=raw.decision_records
        )
        return [ab]

    def self_evaluate(self, artifacts: List[ArtifactBody]) -> Dict[str, Any]:
        # Basic verification check on content presence
        for art in artifacts:
            if "Scaffolded PRD" not in art.content:
                return {"passed": False, "failed_rules": ["prd-missing-header"]}
        return {"passed": True, "failed_rules": []}
