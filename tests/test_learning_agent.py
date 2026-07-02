import pytest
import json
from typing import Dict, Any, List

from agents.models import AgentState, AgentContext, ArtifactMetadata
from agents.factory import AgentFactory
from agents.session_adapter import SessionStateAdapter
from agents.learning import LearningAgent
from tests.test_agent_framework import MockBrainServiceClient, MockMcpResolver

class LearningMockResolver(MockMcpResolver):
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
            return {"content": ""}
        return super().call_tool(server, tool_name, args)

def test_learning_agent_report_generation():
    brain = MockBrainServiceClient()
    resolver = LearningMockResolver()
    
    # 1. Setup minimal inputs to verify structure
    resolver.mock_files["docs/05_evaluation_report.md"] = (
        "# Evaluation Report\n\n"
        "## 3. Issues Detected\n"
        "None\n"
    )
    resolver.mock_files["docs/04_execution_report.md"] = (
        "# Runtime Validation Report\n\n"
        "## 2. Validation Checks\n"
        "- [x] Configuration Loaded: PASSED\n"
        "- [x] Python Imports Valid: PASSED\n"
    )
    resolver.mock_files["docs/06_repair_decision.json"] = json.dumps({
        "repair_status": "no_action",
        "issues_detected": [],
        "fixes_applied": [],
        "retry_required": False
    })

    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("learning_agent", LearningAgent)

    state_adapter = SessionStateAdapter({
        "session_id": "sess_learn_1",
        "project_id": "proj_learn_1"
    })
    agent = factory.create_by_name("learning_agent", "sess_learn_1", "learning_node", state_adapter)
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_learn_1", file_path="docs/05_evaluation_report.md", version=1, checksum="c1", type="evaluation_report", generated_by="evaluation_agent"),
            ArtifactMetadata(id="a-2", session_id="sess_learn_1", file_path="docs/04_execution_report.md", version=1, checksum="c2", type="execution_report", generated_by="runtime_validation_agent"),
            ArtifactMetadata(id="a-3", session_id="sess_learn_1", file_path="docs/06_repair_decision.json", version=1, checksum="c3", type="repair_decision", generated_by="repair_agent")
        ],
        task_instruction="Extract execution history patterns",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)

    assert len(artifacts) == 1
    report_artifact = artifacts[0]
    assert report_artifact.artifact_type == "learning_report"
    assert report_artifact.file_path == "docs/07_learning_report.json"

    data = json.loads(report_artifact.content)
    assert "failure_patterns" in data
    assert "fix_patterns" in data
    assert "success_patterns" in data
    assert "recommendations_for_future_runs" in data

def test_learning_agent_pattern_extraction():
    brain = MockBrainServiceClient()
    resolver = LearningMockResolver()
    
    # Setup inputs containing multiple instances of failures and fixes
    resolver.mock_files["docs/05_evaluation_report.md"] = (
        "# Evaluation Report\n\n"
        "## 3. Issues Detected\n"
        "- Missing Entity class/schema for 'User' in models.py.\n"
        "- Missing Entity class/schema for 'Order' in models.py.\n"
    )
    resolver.mock_files["docs/04_execution_report.md"] = (
        "# Runtime Validation Report\n\n"
        "## 2. Validation Checks\n"
        "- [x] Configuration Loaded: PASSED\n"
        "- [x] Python Imports Valid: PASSED\n"
    )
    # Using repair_decision.json to provide multiple instances of fixes
    resolver.mock_files["docs/06_repair_decision.json"] = json.dumps({
        "repair_status": "repaired",
        "issues_detected": [
            "Missing Entity class: User",
            "Missing Entity class: Order"
        ],
        "fixes_applied": [
            "Entity class 'User' added to backend/app/models.py",
            "Entity class 'Order' added to backend/app/models.py"
        ],
        "retry_required": True
    })

    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("learning_agent", LearningAgent)

    state_adapter = SessionStateAdapter({
        "session_id": "sess_learn_2",
        "project_id": "proj_learn_2"
    })
    agent = factory.create_by_name("learning_agent", "sess_learn_2", "learning_node", state_adapter)
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_learn_2", file_path="docs/05_evaluation_report.md", version=1, checksum="c1", type="evaluation_report", generated_by="evaluation_agent"),
            ArtifactMetadata(id="a-2", session_id="sess_learn_2", file_path="docs/04_execution_report.md", version=1, checksum="c2", type="execution_report", generated_by="runtime_validation_agent"),
            ArtifactMetadata(id="a-3", session_id="sess_learn_2", file_path="docs/06_repair_decision.json", version=1, checksum="c3", type="repair_decision", generated_by="repair_agent")
        ],
        task_instruction="Extract execution history patterns",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)
    
    data = json.loads(artifacts[0].content)
    
    # Assert multi-instance failure patterns are extracted
    assert any("database entity/model omissions" in pat for pat in data["failure_patterns"])
    # Assert multi-instance fix patterns are extracted
    assert any("database entity models" in pat for pat in data["fix_patterns"])
    # Assert success patterns from passed validation checks
    assert len(data["success_patterns"]) > 0

def test_learning_agent_no_side_effects():
    brain = MockBrainServiceClient()
    resolver = LearningMockResolver()
    
    resolver.mock_files["docs/05_evaluation_report.md"] = "# Evaluation\n"
    resolver.mock_files["docs/04_execution_report.md"] = "# Execution\n"
    resolver.mock_files["docs/06_repair_decision.json"] = "{}"

    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("learning_agent", LearningAgent)

    state_adapter = SessionStateAdapter({
        "session_id": "sess_learn_3",
        "project_id": "proj_learn_3"
    })
    agent = factory.create_by_name("learning_agent", "sess_learn_3", "learning_node", state_adapter)
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_learn_3", file_path="docs/05_evaluation_report.md", version=1, checksum="c1", type="evaluation_report", generated_by="evaluation_agent"),
            ArtifactMetadata(id="a-2", session_id="sess_learn_3", file_path="docs/04_execution_report.md", version=1, checksum="c2", type="execution_report", generated_by="runtime_validation_agent"),
            ArtifactMetadata(id="a-3", session_id="sess_learn_3", file_path="docs/06_repair_decision.json", version=1, checksum="c3", type="repair_decision", generated_by="repair_agent")
        ],
        task_instruction="Extract execution history patterns",
        raw_markdown="# Task",
        context_size_chars=10
    )

    # Run lifecycle
    agent.execute_lifecycle("sess_learn_3", "learning_node")

    # 1. Assert NO decision records are stored in Project Brain
    assert len(brain.decisions) == 0

    # 2. Assert NO code modifications or repair activities occurred
    # Verify written files contains only our learning report JSON and nothing else (e.g. no models.py, etc.)
    assert list(resolver.written_files.keys()) == ["docs/07_learning_report.json"]

def test_learning_agent_structured_input_usage():
    brain = MockBrainServiceClient()
    resolver = LearningMockResolver()
    
    resolver.mock_files["docs/05_evaluation_report.md"] = "# Evaluation\n"
    resolver.mock_files["docs/04_execution_report.md"] = "# Execution\n"
    
    # Structured repair decision with 2 issues
    resolver.mock_files["docs/06_repair_decision.json"] = json.dumps({
        "repair_status": "repaired",
        "issues_detected": [
            "Missing Entity class: User",
            "Missing Entity class: Order"
        ],
        "fixes_applied": [
            "Entity class 'User' added to backend/app/models.py",
            "Entity class 'Order' added to backend/app/models.py"
        ],
        "retry_required": True
    })

    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("learning_agent", LearningAgent)

    state_adapter = SessionStateAdapter({
        "session_id": "sess_learn_4",
        "project_id": "proj_learn_4"
    })
    agent = factory.create_by_name("learning_agent", "sess_learn_4", "learning_node", state_adapter)
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_learn_4", file_path="docs/05_evaluation_report.md", version=1, checksum="c1", type="evaluation_report", generated_by="evaluation_agent"),
            ArtifactMetadata(id="a-2", session_id="sess_learn_4", file_path="docs/04_execution_report.md", version=1, checksum="c2", type="execution_report", generated_by="runtime_validation_agent"),
            ArtifactMetadata(id="a-3", session_id="sess_learn_4", file_path="docs/06_repair_decision.json", version=1, checksum="c3", type="repair_decision", generated_by="repair_agent")
        ],
        task_instruction="Extract execution history patterns",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)
    
    data = json.loads(artifacts[0].content)
    
    # Verify it parsed the JSON successfully and extracted patterns from it
    assert len(data["failure_patterns"]) > 0
    assert len(data["fix_patterns"]) > 0

def test_conductor_learning_integration():
    from agents.planning import PlanningAgent
    from agents.blueprint import BlueprintAgent
    from agents.implementation import ImplementationAgent
    from agents.runtime_validation import RuntimeValidationAgent
    from agents.evaluation import EvaluationAgent
    from agents.repair import RepairAgent
    from agents.conductor import Conductor
    from tests.test_conductor_integration import ConductorMockResolver

    brain = MockBrainServiceClient()
    resolver = ConductorMockResolver()
    factory = AgentFactory(brain, mcp_resolver=resolver)
    
    # Register all agents in factory and project brain mock registry
    factory.register_agent_class("Planning Agent", PlanningAgent)
    brain.registered_manifests["Planning Agent"] = factory._create_stub_manifest_dict("Planning Agent", ["prd"])
    
    factory.register_agent_class("Blueprint Agent", BlueprintAgent)
    brain.registered_manifests["Blueprint Agent"] = factory._create_stub_manifest_dict("Blueprint Agent", ["blueprint_agent"])

    factory.register_agent_class("implementation_agent", ImplementationAgent)
    brain.registered_manifests["implementation_agent"] = factory._create_stub_manifest_dict("implementation_agent", ["implementation_agent"])

    factory.register_agent_class("runtime_validation_agent", RuntimeValidationAgent)
    brain.registered_manifests["runtime_validation_agent"] = factory._create_stub_manifest_dict("runtime_validation_agent", ["runtime_validation_agent"])

    factory.register_agent_class("evaluation_agent", EvaluationAgent)
    brain.registered_manifests["evaluation_agent"] = factory._create_stub_manifest_dict("evaluation_agent", ["evaluation_agent"])

    factory.register_agent_class("repair_agent", RepairAgent)
    brain.registered_manifests["repair_agent"] = factory._create_stub_manifest_dict("repair_agent", ["repair_agent"])

    factory.register_agent_class("learning_agent", LearningAgent)
    brain.registered_manifests["learning_agent"] = factory._create_stub_manifest_dict("learning_agent", ["learning_agent"])
    
    conductor = Conductor(brain_client=brain, agent_factory=factory)
    
    response = conductor.run(
        product_idea="Build an ordering system",
        project_id="proj_integrate_123",
        session_id="sess_integrate_123"
    )
    
    assert response["status"] == "success"
    assert response["session_id"] == "sess_integrate_123"
    
    # 7 artifacts: Planning, Blueprint, Implementation, Validation, Evaluation, Repair, Learning
    assert len(response["artifacts"]) == 7
    
    learning_artifact = next(a for a in response["artifacts"] if a["type"] == "learning_report")
    assert learning_artifact["generated_by"] == "learning_agent"
    assert learning_artifact["file_path"] == "docs/07_learning_report.json"
    
    # Verify the contents written to the resolver's files
    assert "docs/07_learning_report.json" in resolver.written_files
    report_data = json.loads(resolver.written_files["docs/07_learning_report.json"])
    assert "failure_patterns" in report_data
    assert "fix_patterns" in report_data
    assert "success_patterns" in report_data
    assert "recommendations_for_future_runs" in report_data

