import pytest
import json
from typing import Dict, Any, List

from agents.models import AgentState, AgentContext, ArtifactMetadata
from agents.factory import AgentFactory
from agents.session_adapter import SessionStateAdapter
from agents.predictive import PredictiveAgent
from tests.test_agent_framework import MockBrainServiceClient, MockMcpResolver

class PredictiveMockResolver(MockMcpResolver):
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
            raise Exception("File not found")
        return super().call_tool(server, tool_name, args)

def setup_agent_context(session_id: str, project_id: str, resolver: PredictiveMockResolver) -> PredictiveAgent:
    brain = MockBrainServiceClient()
    
    # Register manifest in brain mock registry
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("predictive_agent", PredictiveAgent)
    
    state_adapter = SessionStateAdapter({
        "session_id": session_id,
        "project_id": project_id
    })
    
    agent = factory.create_by_name("predictive_agent", session_id, "predictive_node", state_adapter)
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id=session_id, file_path="docs/02_system_design.md", version=1, checksum="c1", type="system_design", generated_by="blueprint_agent"),
            ArtifactMetadata(id="a-2", session_id=session_id, file_path="docs/07_learning_report.json", version=1, checksum="c2", type="learning_report", generated_by="learning_agent")
        ],
        task_instruction="Analyze system design and historical learning data",
        raw_markdown="# Task",
        context_size_chars=10
    )
    
    return agent

def test_predictive_agent_risk_scoring():
    # Setup resolver with blueprint containing components and implementations containing some missing ones
    resolver = PredictiveMockResolver()
    resolver.mock_files["docs/02_system_design.md"] = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- POST /api/v1/orders (creates order)\n"
        "- GET /api/v1/orders/{id} (gets status)\n\n"
        "## 3. Data Models\n"
        "- User (id, name, email)\n"
        "- Order (id, customer_id, status)\n\n"
        "## 4. Service Decomposition\n"
        "- OrderService (processes orders)\n\n"
        "## 5. Configuration\n"
        "- ENV\n"
        "- DATABASE_URL\n"
    )
    resolver.mock_files["docs/07_learning_report.json"] = json.dumps({
        "failure_patterns": [],
        "fix_patterns": [],
        "success_patterns": [],
        "recommendations_for_future_runs": []
    })
    
    # Implementations:
    # api.py matches only GET /api/v1/orders/{id} (POST is missing) -> 1/2 missing (api risk = 5.0)
    resolver.mock_files["backend/app/api.py"] = "router.get('/api/v1/orders/{id}')"
    # models.py has User but no Order -> 1/2 missing (db risk = 5.0)
    resolver.mock_files["backend/app/models.py"] = "class User(Base):"
    # services.py matches OrderService -> 0/1 missing (services risk = 0.0)
    resolver.mock_files["backend/app/services.py"] = "class OrderService:"
    # .env matches DATABASE_URL but ENV is missing -> 1/2 missing (config risk = 5.0)
    resolver.mock_files["backend/.env"] = "DATABASE_URL=sqlite://"
    
    agent = setup_agent_context("sess_scoring", "proj_scoring", resolver)
    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)
    
    assert len(artifacts) == 1
    report = json.loads(artifacts[0].content)
    
    # Overall risk should be average of category risks: (5 + 5 + 0 + 5) / 4 = 3.75
    assert report["risk_score"] == 3.75
    # High-risk components are those >= 5.0 (api, database, config)
    high_risk_names = [c["name"] for c in report["high_risk_components"]]
    assert "api" in high_risk_names
    assert "database" in high_risk_names
    assert "config" in high_risk_names
    assert "services" not in high_risk_names
    
    # Verify predictions and warnings lists
    assert len(report["failure_predictions"]) == 3  # missing POST order, missing Order entity, missing ENV config
    assert len(report["preventive_recommendations"]) >= 3

def test_predictive_agent_no_side_effects():
    resolver = PredictiveMockResolver()
    resolver.mock_files["docs/02_system_design.md"] = (
        "# Blueprint\n"
        "## 2. API Design\n"
        "- GET /api/v1/orders\n"
    )
    resolver.mock_files["docs/07_learning_report.json"] = "{}"
    resolver.mock_files["backend/app/api.py"] = "/api/v1/orders"
    resolver.mock_files["backend/app/models.py"] = ""
    resolver.mock_files["backend/app/services.py"] = ""
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

def test_predictive_agent_learning_integration():
    resolver = PredictiveMockResolver()
    resolver.mock_files["docs/02_system_design.md"] = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- POST /api/v1/orders\n"
    )
    
    # Failures matched in learning report: "database entity/model omissions in models schema" and "endpoint missing"
    # Wait, in the test context, let's trigger endpoints failure pattern
    resolver.mock_files["docs/07_learning_report.json"] = json.dumps({
        "failure_patterns": [
            "Multiple missing API endpoint routes detected in backend application."
        ]
    })
    
    # API implementation is missing -> base api risk = 10.0
    resolver.mock_files["backend/app/api.py"] = ""
    resolver.mock_files["backend/app/models.py"] = ""
    resolver.mock_files["backend/app/services.py"] = ""
    resolver.mock_files["backend/.env"] = ""
    
    agent = setup_agent_context("sess_learn", "proj_learn", resolver)
    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)
    
    report = json.loads(artifacts[0].content)
    
    # Since api is missing and api failure pattern matches, api risk score is base (10.0) * multiplier (1.5) = 15.0 capped at 10.0
    # Let's verify that the historical pattern matched multiplier is applied
    # Let's check with a smaller base score, e.g. 1 out of 2 missing -> base is 5.0. 5.0 * 1.5 = 7.5.
    # Let's adjust mock files to test 5.0 * 1.5 = 7.5.
    resolver.mock_files["docs/02_system_design.md"] = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- POST /api/v1/orders\n"
        "- GET /api/v1/orders\n"
    )
    resolver.mock_files["backend/app/api.py"] = "router.get('/api/v1/orders')"  # POST is missing. Base score = 5.0
    resolver.mock_files["backend/app/models.py"] = ""
    resolver.mock_files["backend/app/services.py"] = ""
    resolver.mock_files["backend/.env"] = "ENV=development\nDATABASE_URL=sqlite://\nHOST=0.0.0.0\nPORT=8000"
    
    agent = setup_agent_context("sess_learn_mult", "proj_learn_mult", resolver)
    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)
    report = json.loads(artifacts[0].content)
    
    # The api category score is 7.5 (because base 5.0 * 1.5 multiplier).
    # Since api is the only component defined in design, overall risk score should be average:
    # api_risk (7.5) + db (0) + svc (0) + cfg (0) = 7.5 / 4 = 1.875
    assert report["risk_score"] == 1.88  # rounded to 2 decimals

def test_predictive_agent_missing_file_handling():
    resolver = PredictiveMockResolver()
    
    # Supply blueprint but NO implementation files or learning reports in mock files!
    # They should not exist, which will raise "File not found" in resolver.
    resolver.mock_files["docs/02_system_design.md"] = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- POST /api/v1/orders\n"
    )
    
    agent = setup_agent_context("sess_missing_files", "proj_missing_files", resolver)
    plan = agent.plan(agent.context)
    agent.tools.open()
    
    # Execute should run successfully and NOT raise Exception for missing files
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)
    
    assert len(artifacts) == 1
    report = json.loads(artifacts[0].content)
    
    # Missing files are treated as high-risk signals: all category scores default to 10.0
    # Overall risk score is 10.0
    assert report["risk_score"] == 10.0
    # Warnings should contain missing file signals
    assert any("backend/app/api.py" in w and "missing" in w for w in report["warnings"])
    assert any("backend/app/models.py" in w and "missing" in w for w in report["warnings"])
