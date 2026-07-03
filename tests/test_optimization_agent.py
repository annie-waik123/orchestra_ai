import pytest
import json
from typing import Dict, Any, List

from agents.models import AgentState, AgentContext, ArtifactMetadata
from agents.factory import AgentFactory
from agents.session_adapter import SessionStateAdapter
from agents.optimization import OptimizationAgent
from tests.test_agent_framework import MockBrainServiceClient, MockMcpResolver

class OptimizationMockResolver(MockMcpResolver):
    def __init__(self):
        super().__init__()
        self.written_files = {}
        self.mock_files = {}

    def call_tool(self, server: str, tool_name: str, args: Dict[str, Any]) -> Any:
        if tool_name == "write_file":
            self.written_files[args["path"]] = args["content"]
            return "File written successfully"
        elif tool_name == "read_file":
            path = args["path"]
            if path in self.written_files:
                return {"content": self.written_files[path]}
            if path in self.mock_files:
                return {"content": self.mock_files[path]}
            raise Exception(f"File not found: {path}")
        return super().call_tool(server, tool_name, args)

def setup_agent_context(session_id: str, project_id: str, resolver: OptimizationMockResolver) -> OptimizationAgent:
    brain = MockBrainServiceClient()
    
    # Register manifest in brain mock registry
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("optimization_agent", OptimizationAgent)
    
    state_adapter = SessionStateAdapter({
        "session_id": session_id,
        "project_id": project_id
    })
    
    agent = factory.create_by_name("optimization_agent", session_id, "optimization_node", state_adapter)
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id=session_id, file_path="docs/01_prd.md", version=1, checksum="c1", type="prd", generated_by="Planning Agent"),
            ArtifactMetadata(id="a-2", session_id=session_id, file_path="docs/02_system_design.md", version=1, checksum="c2", type="system_design", generated_by="blueprint_agent"),
            ArtifactMetadata(id="a-3", session_id=session_id, file_path="docs/03_backend_scaffold.md", version=1, checksum="c3", type="backend_scaffold", generated_by="implementation_agent"),
            ArtifactMetadata(id="a-4", session_id=session_id, file_path="docs/07_learning_report.json", version=1, checksum="c4", type="learning_report", generated_by="learning_agent"),
            ArtifactMetadata(id="a-5", session_id=session_id, file_path="docs/08_prediction_report.json", version=1, checksum="c5", type="prediction_report", generated_by="predictive_agent")
        ],
        task_instruction="Analyze system design and backend code scaffold for optimization opportunities",
        raw_markdown="# Task",
        context_size_chars=10
    )
    
    return agent

def test_optimization_report_generation():
    resolver = OptimizationMockResolver()
    resolver.mock_files["docs/01_prd.md"] = "# Product Requirements Document\nVersion 1.0"
    resolver.mock_files["docs/02_system_design.md"] = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- GET /orders (gets orders)\n"
        "## 3. Data Models\n"
        "- Order (id, customer_id)\n"
    )
    resolver.mock_files["docs/03_backend_scaffold.md"] = "## Generated File Structure\n- backend/app/api.py\n"
    resolver.mock_files["docs/07_learning_report.json"] = "{}"
    resolver.mock_files["docs/08_prediction_report.json"] = '{"risk_score": 0.0}'
    
    # Implementations:
    # api.py matches GET /orders (no prefix versioning) -> API design penalty
    resolver.mock_files["backend/app/api.py"] = "@router.get('/orders')\ndef read_orders():\n    pass"
    resolver.mock_files["backend/app/models.py"] = ""
    resolver.mock_files["backend/app/services.py"] = ""
    resolver.mock_files["backend/app/config.py"] = ""
    resolver.mock_files["backend/app/main.py"] = ""
    resolver.mock_files["backend/.env"] = ""

    agent = setup_agent_context("sess_gen", "proj_gen", resolver)
    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)
    
    assert len(artifacts) == 1
    report = json.loads(artifacts[0].content)
    
    assert "overall_optimization_score" in report
    assert "confidence" in report
    assert "optimization_opportunities" in report
    assert "architectural_recommendations" in report
    assert "maintainability_recommendations" in report
    assert "performance_recommendations" in report
    assert "future_scalability_recommendations" in report

def test_scoring_algorithm_correctness():
    resolver = OptimizationMockResolver()
    resolver.mock_files["docs/01_prd.md"] = "# Product Requirements Document\nPRD contains specifications."
    # API Design has 2 non-REST endpoints (verbs in paths) -> HIGH penalty (1.5)
    # API Design also lacks version prefix -> MEDIUM penalty (1.0)
    # API Category total penalty = 1.5 + 1.0 = 2.5 capped at 2.0.
    resolver.mock_files["docs/02_system_design.md"] = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- GET /create_order\n"
        "- GET /delete_order\n"
        "## 3. Data Models\n"
        "- Order (id, customer_id)\n"
    )
    resolver.mock_files["docs/03_backend_scaffold.md"] = "## Generated File Structure\n- backend/app/api.py\n"
    resolver.mock_files["docs/07_learning_report.json"] = "{}"
    resolver.mock_files["docs/08_prediction_report.json"] = '{"risk_score": 0.0}'
    
    resolver.mock_files["backend/app/api.py"] = "router.get('/create_order')"
    resolver.mock_files["backend/app/models.py"] = ""
    resolver.mock_files["backend/app/services.py"] = ""
    resolver.mock_files["backend/app/config.py"] = ""
    resolver.mock_files["backend/app/main.py"] = ""
    resolver.mock_files["backend/.env"] = ""

    agent = setup_agent_context("sess_scoring", "proj_scoring", resolver)
    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    
    # Check that category penalty was capped at 2.0 instead of 2.5
    # Overall score = 10.0 - 2.0 = 8.0
    assert raw.content_blocks["overall_optimization_score"] == 8.0

def test_confidence_calculation():
    # Test confidence calculation when artifacts are missing or incomplete
    resolver = OptimizationMockResolver()
    
    # 1. All artifacts complete: confidence should be 1.0 (with no booster)
    resolver.mock_files["docs/01_prd.md"] = "# Product Requirements Document\nThis is a long description of product requirements that exceeds one hundred characters in total length to avoid triggering any completeness warnings or deductions."
    resolver.mock_files["docs/02_system_design.md"] = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- GET /api/v1/orders\n"
        "## 3. Data Models\n"
        "- Order (id, customer_id)\n"
    )
    resolver.mock_files["docs/03_backend_scaffold.md"] = "## Generated File Structure\n- backend/app/api.py\n"
    resolver.mock_files["docs/07_learning_report.json"] = "{}"
    resolver.mock_files["docs/08_prediction_report.json"] = '{"risk_score": 0.0}'
    resolver.mock_files["backend/app/api.py"] = ""
    resolver.mock_files["backend/app/models.py"] = ""
    resolver.mock_files["backend/app/services.py"] = ""
    resolver.mock_files["backend/app/config.py"] = ""
    resolver.mock_files["backend/app/main.py"] = ""
    resolver.mock_files["backend/.env"] = ""

    agent = setup_agent_context("sess_conf_full", "proj_conf_full", resolver)
    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    assert raw.content_blocks["confidence"] == 1.0

    # 2. PRD incomplete, learning report missing -> confidence should be lower
    resolver.mock_files["docs/01_prd.md"] = "too short" # Incomplete (-0.1)
    if "docs/07_learning_report.json" in resolver.mock_files:
        del resolver.mock_files["docs/07_learning_report.json"]
    # Overall deduction: -0.3. Final confidence: 1.0 - 0.3 = 0.7
    agent = setup_agent_context("sess_conf_part", "proj_conf_part", resolver)
    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    assert raw.content_blocks["confidence"] == 0.7

def test_no_side_effects():
    resolver = OptimizationMockResolver()
    resolver.mock_files["docs/01_prd.md"] = "# Product Requirements Document\nThis is a product description."
    resolver.mock_files["docs/02_system_design.md"] = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- GET /api/v1/orders\n"
        "## 3. Data Models\n"
        "- Order (id, customer_id)\n"
    )
    resolver.mock_files["docs/03_backend_scaffold.md"] = "## Generated File Structure\n"
    resolver.mock_files["docs/07_learning_report.json"] = "{}"
    resolver.mock_files["docs/08_prediction_report.json"] = '{"risk_score": 0.0}'
    resolver.mock_files["backend/app/api.py"] = ""
    resolver.mock_files["backend/app/models.py"] = ""
    resolver.mock_files["backend/app/services.py"] = ""
    resolver.mock_files["backend/app/config.py"] = ""
    resolver.mock_files["backend/app/main.py"] = ""
    resolver.mock_files["backend/.env"] = ""

    agent = setup_agent_context("sess_no_side", "proj_no_side", resolver)
    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)
    
    assert len(artifacts) == 1
    # Check that decision_records are empty (strictly advisory)
    assert len(raw.decision_records) == 0
    assert len(artifacts[0].decisions) == 0

def test_learning_integration():
    resolver = OptimizationMockResolver()
    resolver.mock_files["docs/01_prd.md"] = "# Product Requirements Document\nPRD specification that exceeds one hundred characters in total length to avoid triggering any completeness warnings or deductions."
    resolver.mock_files["docs/02_system_design.md"] = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- GET /create_order\n"
        "## 3. Data Models\n"
        "- Order (id, customer_id)\n"
    )
    resolver.mock_files["docs/03_backend_scaffold.md"] = "## Generated File Structure\n- backend/app/api.py\n"
    resolver.mock_files["docs/07_learning_report.json"] = "{}"
    # Omit docs/08_prediction_report.json to test boost with deduction
    resolver.mock_files["backend/app/api.py"] = "router.get('/create_order')"
    resolver.mock_files["backend/app/models.py"] = ""
    resolver.mock_files["backend/app/services.py"] = ""
    resolver.mock_files["backend/app/config.py"] = ""
    resolver.mock_files["backend/app/main.py"] = ""
    resolver.mock_files["backend/.env"] = ""

    agent = setup_agent_context("sess_learn", "proj_learn", resolver)
    
    # Mock historical artifacts containing optimization pattern match: "RESTful resource noun routing"
    mock_lr = {
        "optimization_patterns": ["RESTful resource noun routing"]
    }
    
    # Store in mock brain
    art_data = {
        "id": "h-1",
        "session_id": "sess_hist_1",
        "type": "learning_report",
        "content": json.dumps(mock_lr)
    }
    agent.brain_client.artifacts["h-1"] = art_data

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    
    opps = raw.content_blocks["optimization_opportunities"]
    api_opp = next(o for o in opps if o["category"] == "api" and "RESTful" in o["recommendation"])
    
    # The matching pattern should upgrade the priority to HIGH and boost confidence
    assert api_opp["priority"] == "HIGH"
    # Confidence boost of 0.05 applied (base 1.0 - 0.2 deduction + 0.05 boost = 0.85)
    assert raw.content_blocks["confidence"] == 0.85

def test_deterministic_output():
    resolver = OptimizationMockResolver()
    resolver.mock_files["docs/01_prd.md"] = "# Product Requirements Document\nStandard specs here."
    resolver.mock_files["docs/02_system_design.md"] = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- GET /create_order\n"
        "## 3. Data Models\n"
        "- Order (id, customer_id)\n"
    )
    resolver.mock_files["docs/03_backend_scaffold.md"] = "## Generated File Structure\n"
    resolver.mock_files["docs/07_learning_report.json"] = "{}"
    resolver.mock_files["docs/08_prediction_report.json"] = '{"risk_score": 0.0}'
    resolver.mock_files["backend/app/api.py"] = "router.get('/create_order')"
    resolver.mock_files["backend/app/models.py"] = ""
    resolver.mock_files["backend/app/services.py"] = ""
    resolver.mock_files["backend/app/config.py"] = ""
    resolver.mock_files["backend/app/main.py"] = ""
    resolver.mock_files["backend/.env"] = ""

    agent = setup_agent_context("sess_det", "proj_det", resolver)
    agent.tools.open()
    
    plan1 = agent.plan(agent.context)
    raw1 = agent.execute(plan1)
    
    plan2 = agent.plan(agent.context)
    raw2 = agent.execute(plan2)
    
    # Check that outputs are identical
    assert raw1.content_blocks["overall_optimization_score"] == raw2.content_blocks["overall_optimization_score"]
    assert len(raw1.content_blocks["optimization_opportunities"]) == len(raw2.content_blocks["optimization_opportunities"])
