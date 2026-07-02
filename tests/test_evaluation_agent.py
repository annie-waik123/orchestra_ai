import pytest
from typing import Dict, Any, List
from agents.models import AgentState, AgentContext, ArtifactMetadata
from agents.factory import AgentFactory
from agents.session_adapter import SessionStateAdapter
from agents.evaluation import EvaluationAgent
from tests.test_agent_framework import MockBrainServiceClient, MockMcpResolver

class EvaluationMockResolver(MockMcpResolver):
    def __init__(self):
        super().__init__()
        self.mock_files = {
            "docs/01_prd.md": "PRD scoping info",
            "docs/02_system_design.md": (
                "# System Design Blueprint\n\n"
                "## 2. API Design\n"
                "- POST /api/v1/orders (creates order)\n"
                "- GET /api/v1/orders/{id} (gets status)\n\n"
                "## 3. Data Models\n"
                "- User (id, name, email)\n"
                "- Order (id, customer_id, status)\n\n"
                "## 4. Service Decomposition\n"
                "- OrderService: processes orders\n"
            ),
            "docs/03_backend_scaffold.md": (
                "# Backend Scaffold Summary\n\n"
                "## Generated File Structure\n"
                "- backend/.env\n"
                "- backend/app/config.py\n"
                "- backend/app/db.py\n"
                "- backend/app/models.py\n"
                "- backend/app/services.py\n"
                "- backend/app/api.py\n"
                "- backend/app/main.py\n"
            ),
            "docs/04_execution_report.md": (
                "# Runtime Validation Report\n\n"
                "## 1. Summary\n"
                "- **Status**: SUCCESS\n\n"
                "## 2. Validation Checks\n"
                "- [x] Configuration Loaded: PASSED\n"
                "- [x] Python Imports Valid: PASSED\n"
                "- [x] FastAPI App Initialized: PASSED\n"
                "- [x] Routes Loaded: PASSED\n"
            ),
            "backend/app/api.py": (
                "@router.post('/api/v1/orders')\n"
                "def create_order(): pass\n"
                "@router.get('/api/v1/orders/{id}')\n"
                "def get_order(): pass\n"
            ),
            "backend/app/models.py": (
                "class User(Base):\n"
                "    __tablename__ = 'users'\n"
                "class Order(Base):\n"
                "    __tablename__ = 'orders'\n"
            ),
            "backend/app/services.py": (
                "class OrderService:\n"
                "    def execute_logic(self): pass\n"
            ),
            "backend/app/main.py": "app = FastAPI()\n",
            "backend/app/config.py": "settings = Settings()\n",
            "backend/app/db.py": "Base = declarative_base()\n",
            "backend/.env": "DATABASE_URL=sqlite://\n"
        }

    def call_tool(self, server: str, tool_name: str, args: Dict[str, Any]) -> Any:
        if tool_name == "read_file":
            path = args["path"]
            if path in self.mock_files:
                return {"content": self.mock_files[path]}
            raise Exception(f"File not found: {path}")
        return super().call_tool(server, tool_name, args)

def test_evaluation_agent_perfect_pass():
    brain = MockBrainServiceClient()
    resolver = EvaluationMockResolver()
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("evaluation_agent", EvaluationAgent)

    state_dict = {
        "session_id": "sess_eval_1",
        "project_id": "proj_eval_1",
        "node_evaluation_node_task_instruction": "Evaluate the pipeline"
    }
    state_adapter = SessionStateAdapter(state_dict)
    agent = factory.create_by_name("evaluation_agent", "sess_eval_1", "evaluation_node", state_adapter)

    # Populate perfect context
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_eval_1", file_path="docs/01_prd.md", version=1, checksum="c1", type="prd", generated_by="Planning Agent"),
            ArtifactMetadata(id="a-2", session_id="sess_eval_1", file_path="docs/02_system_design.md", version=1, checksum="c2", type="system_design", generated_by="Blueprint Agent", depends_on=["docs/01_prd.md"]),
            ArtifactMetadata(id="a-3", session_id="sess_eval_1", file_path="docs/03_backend_scaffold.md", version=1, checksum="c3", type="backend_scaffold", generated_by="implementation_agent", depends_on=["docs/02_system_design.md"]),
            ArtifactMetadata(id="a-4", session_id="sess_eval_1", file_path="docs/04_execution_report.md", version=1, checksum="c4", type="execution_report", generated_by="runtime_validation_agent", depends_on=["docs/03_backend_scaffold.md"])
        ],
        task_instruction="Evaluate the pipeline",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)

    assert len(artifacts) == 1
    report = artifacts[0]
    assert report.artifact_type == "evaluation_report"
    assert report.file_path == "docs/05_evaluation_report.md"

    # Score breakdown check
    assert "**Overall Score**: 10.0/10.0" in report.content
    assert "**Status**: PASS" in report.content
    assert "**Architecture Consistency**: 3.0/3.0" in report.content
    assert "**Implementation Completeness**: 3.0/3.0" in report.content
    assert "**Runtime Evidence**: 2.0/2.0" in report.content
    assert "**Pipeline Completeness & Lineage**: 2.0/2.0" in report.content
    assert "**Security Check**: NOT_EVALUATED" in report.content


def test_evaluation_agent_partial_mismatch():
    brain = MockBrainServiceClient()
    resolver = EvaluationMockResolver()
    
    # Remove OrderService class definition to simulate architectural mismatch and implementation incompleteness
    resolver.mock_files["backend/app/services.py"] = "# Empty service file\n"
    
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("evaluation_agent", EvaluationAgent)

    state_dict = {
        "session_id": "sess_eval_2",
        "project_id": "proj_eval_2",
        "node_evaluation_node_task_instruction": "Evaluate the pipeline"
    }
    state_adapter = SessionStateAdapter(state_dict)
    agent = factory.create_by_name("evaluation_agent", "sess_eval_2", "evaluation_node", state_adapter)

    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_eval_2", file_path="docs/01_prd.md", version=1, checksum="c1", type="prd", generated_by="Planning Agent"),
            ArtifactMetadata(id="a-2", session_id="sess_eval_2", file_path="docs/02_system_design.md", version=1, checksum="c2", type="system_design", generated_by="Blueprint Agent", depends_on=["docs/01_prd.md"]),
            ArtifactMetadata(id="a-3", session_id="sess_eval_2", file_path="docs/03_backend_scaffold.md", version=1, checksum="c3", type="backend_scaffold", generated_by="implementation_agent", depends_on=["docs/02_system_design.md"]),
            ArtifactMetadata(id="a-4", session_id="sess_eval_2", file_path="docs/04_execution_report.md", version=1, checksum="c4", type="execution_report", generated_by="runtime_validation_agent", depends_on=["docs/03_backend_scaffold.md"])
        ],
        task_instruction="Evaluate the pipeline",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)

    report = artifacts[0]
    # Check that score is strictly less than 10.0 and status is PARTIAL
    assert "**Status**: PARTIAL" in report.content
    assert "Missing Service class 'OrderService' in services.py." in report.content
    assert "Declare class OrderService in backend/app/services.py." in report.content


def test_evaluation_agent_fail_missing_artifact():
    brain = MockBrainServiceClient()
    resolver = EvaluationMockResolver()
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("evaluation_agent", EvaluationAgent)

    state_dict = {
        "session_id": "sess_eval_3",
        "project_id": "proj_eval_3",
        "node_evaluation_node_task_instruction": "Evaluate the pipeline"
    }
    state_adapter = SessionStateAdapter(state_dict)
    agent = factory.create_by_name("evaluation_agent", "sess_eval_3", "evaluation_node", state_adapter)

    # Missing execution_report from artifact metadata
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_eval_3", file_path="docs/01_prd.md", version=1, checksum="c1", type="prd", generated_by="Planning Agent"),
            ArtifactMetadata(id="a-2", session_id="sess_eval_3", file_path="docs/02_system_design.md", version=1, checksum="c2", type="system_design", generated_by="Blueprint Agent", depends_on=["docs/01_prd.md"]),
            ArtifactMetadata(id="a-3", session_id="sess_eval_3", file_path="docs/03_backend_scaffold.md", version=1, checksum="c3", type="backend_scaffold", generated_by="implementation_agent", depends_on=["docs/02_system_design.md"])
        ],
        task_instruction="Evaluate the pipeline",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)

    report = artifacts[0]
    assert "**Status**: FAIL" in report.content
    assert "Missing Execution Report artifact from pipeline." in report.content
