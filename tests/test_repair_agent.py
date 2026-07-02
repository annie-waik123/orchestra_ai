import pytest
import json
from typing import Dict, Any, List

from agents.models import AgentState, AgentContext, ArtifactMetadata
from agents.factory import AgentFactory
from agents.session_adapter import SessionStateAdapter
from agents.repair import RepairAgent
from agents.conductor import Conductor
from agents.planning import PlanningAgent
from agents.blueprint import BlueprintAgent
from agents.implementation import ImplementationAgent
from agents.runtime_validation import RuntimeValidationAgent
from agents.evaluation import EvaluationAgent
from tests.test_agent_framework import MockBrainServiceClient, MockMcpResolver

class RepairMockResolver(MockMcpResolver):
    def __init__(self):
        super().__init__()
        self.written_files = {}

    def call_tool(self, server: str, tool_name: str, args: Dict[str, Any]) -> Any:
        if tool_name == "write_file":
            self.written_files[args["path"]] = args["content"]
            return "File written successfully"
        elif tool_name == "read_file":
            path = args["path"]
            if path in self.written_files:
                return {"content": self.written_files[path]}
            # Return stubs based on path
            if path == "docs/05_evaluation_report.md":
                return {"content": self.written_files.get(path, "Default Eval Report")}
            if path == "docs/04_execution_report.md":
                return {"content": self.written_files.get(path, "Default Exec Report")}
            if path in ["backend/app/models.py", "backend/app/services.py", "backend/app/api.py", "backend/app/main.py", "backend/.env"]:
                return {"content": self.written_files.get(path, "# Existing Content\n")}
            return {"content": ""}
        return super().call_tool(server, tool_name, args)

def test_repair_agent_no_action():
    brain = MockBrainServiceClient()
    resolver = RepairMockResolver()
    
    # Perfect evaluation report with no issues
    resolver.written_files["docs/05_evaluation_report.md"] = (
        "# Evaluation Report\n\n"
        "## 1. Summary\n"
        "- **Overall Score**: 10.0/10.0\n"
        "- **Status**: PASS\n\n"
        "## 3. Issues Detected\n"
        "None\n"
    )
    resolver.written_files["docs/04_execution_report.md"] = (
        "# Runtime Validation Report\n\n"
        "## 2. Validation Checks\n"
        "- [x] Configuration Loaded: PASSED\n"
        "- [x] Python Imports Valid: PASSED\n"
    )

    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("repair_agent", RepairAgent)

    state_adapter = SessionStateAdapter({
        "session_id": "sess_repair_1",
        "project_id": "proj_repair_1"
    })
    agent = factory.create_by_name("repair_agent", "sess_repair_1", "repair_node", state_adapter)
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_repair_1", file_path="docs/05_evaluation_report.md", version=1, checksum="c1", type="evaluation_report", generated_by="evaluation_agent"),
            ArtifactMetadata(id="a-2", session_id="sess_repair_1", file_path="docs/04_execution_report.md", version=1, checksum="c2", type="execution_report", generated_by="runtime_validation_agent")
        ],
        task_instruction="Repair the scaffold",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)

    assert len(artifacts) == 1
    decision_artifact = artifacts[0]
    assert decision_artifact.artifact_type == "repair_decision"
    assert decision_artifact.file_path == "docs/06_repair_decision.json"

    data = json.loads(decision_artifact.content)
    assert data["repair_status"] == "no_action"
    assert data["retry_required"] is False
    assert len(data["issues_detected"]) == 0

def test_repair_agent_successful_fix():
    brain = MockBrainServiceClient()
    resolver = RepairMockResolver()
    
    # Configure mock file contents
    resolver.written_files["backend/app/models.py"] = "class ExistingModel(Base):\n    pass\n"
    resolver.written_files["backend/app/services.py"] = "# services\n"
    resolver.written_files["backend/app/api.py"] = "# api routes\n"

    # Evaluation report showing missing components
    resolver.written_files["docs/05_evaluation_report.md"] = (
        "# Evaluation Report\n\n"
        "## 3. Issues Detected\n"
        "- Missing Entity class/schema for 'User' in models.py.\n"
        "- Missing Service class 'OrderService' in services.py.\n"
        "- Missing API endpoint GET /api/v1/orders in api.py.\n"
    )
    resolver.written_files["docs/04_execution_report.md"] = (
        "# Runtime Validation Report\n\n"
        "## 2. Validation Checks\n"
        "- [x] Configuration Loaded: PASSED\n"
    )

    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("repair_agent", RepairAgent)

    state_adapter = SessionStateAdapter({
        "session_id": "sess_repair_2",
        "project_id": "proj_repair_2"
    })
    agent = factory.create_by_name("repair_agent", "sess_repair_2", "repair_node", state_adapter)
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_repair_2", file_path="docs/05_evaluation_report.md", version=1, checksum="c1", type="evaluation_report", generated_by="evaluation_agent"),
            ArtifactMetadata(id="a-2", session_id="sess_repair_2", file_path="docs/04_execution_report.md", version=1, checksum="c2", type="execution_report", generated_by="runtime_validation_agent")
        ],
        task_instruction="Repair the scaffold",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)

    decision_artifact = artifacts[0]
    data = json.loads(decision_artifact.content)

    assert data["repair_status"] == "repaired"
    assert data["retry_required"] is True
    assert len(data["fixes_applied"]) == 3
    
    # Check that fixes were written to resolver's files via ToolManager
    models_content = resolver.written_files["backend/app/models.py"]
    assert "class User(Base):" in models_content
    assert "class UserSchema(BaseModel):" in models_content
    
    services_content = resolver.written_files["backend/app/services.py"]
    assert "class OrderService:" in services_content

    api_content = resolver.written_files["backend/app/api.py"]
    assert "@router.get('/api/v1/orders')" in api_content

def test_repair_agent_partial_fix():
    brain = MockBrainServiceClient()
    resolver = RepairMockResolver()
    
    # Evaluation report containing both repairable and unrepairable issues
    resolver.written_files["docs/05_evaluation_report.md"] = (
        "# Evaluation Report\n\n"
        "## 3. Issues Detected\n"
        "- Missing Entity class/schema for 'Product' in models.py.\n"
        "- Security Check: FAILED. High risk vulnerability in packages.\n"
    )
    resolver.written_files["docs/04_execution_report.md"] = (
        "# Runtime Validation Report\n\n"
        "## 2. Validation Checks\n"
        "- [x] Configuration Loaded: PASSED\n"
    )

    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("repair_agent", RepairAgent)

    state_adapter = SessionStateAdapter({
        "session_id": "sess_repair_3",
        "project_id": "proj_repair_3"
    })
    agent = factory.create_by_name("repair_agent", "sess_repair_3", "repair_node", state_adapter)
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_repair_3", file_path="docs/05_evaluation_report.md", version=1, checksum="c1", type="evaluation_report", generated_by="evaluation_agent"),
            ArtifactMetadata(id="a-2", session_id="sess_repair_3", file_path="docs/04_execution_report.md", version=1, checksum="c2", type="execution_report", generated_by="runtime_validation_agent")
        ],
        task_instruction="Repair the scaffold",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)

    decision_artifact = artifacts[0]
    data = json.loads(decision_artifact.content)

    # It should still mark as repaired since it repaired the missing entity
    assert data["repair_status"] == "repaired"
    assert data["retry_required"] is True
    assert "Add missing entity class and schema for Product" in data["fixes_applied"]
    assert "class Product(Base):" in resolver.written_files["backend/app/models.py"]

def test_repair_agent_failure_handling():
    brain = MockBrainServiceClient()
    resolver = RepairMockResolver()
    
    # Make tool resolver raise errors when writing files to simulate filesystem write failure
    orig_call_tool = resolver.call_tool
    def failing_call_tool(server: str, tool_name: str, args: Dict[str, Any]) -> Any:
        if tool_name == "write_file":
            raise Exception("Disk write error")
        return orig_call_tool(server, tool_name, args)
        
    resolver.call_tool = failing_call_tool

    # Evaluation report showing issues
    resolver.written_files["docs/05_evaluation_report.md"] = (
        "# Evaluation Report\n\n"
        "## 3. Issues Detected\n"
        "- Missing Entity class/schema for 'User' in models.py.\n"
    )

    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("repair_agent", RepairAgent)

    state_adapter = SessionStateAdapter({
        "session_id": "sess_repair_4",
        "project_id": "proj_repair_4"
    })
    agent = factory.create_by_name("repair_agent", "sess_repair_4", "repair_node", state_adapter)
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(id="a-1", session_id="sess_repair_4", file_path="docs/05_evaluation_report.md", version=1, checksum="c1", type="evaluation_report", generated_by="evaluation_agent")
        ],
        task_instruction="Repair the scaffold",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)

    decision_artifact = artifacts[0]
    data = json.loads(decision_artifact.content)

    assert data["repair_status"] == "failed"
    assert data["retry_required"] is False

def test_repair_loop_conductor_integration():
    brain = MockBrainServiceClient()
    
    class LoopIntegrationMockResolver(MockMcpResolver):
        def __init__(self):
            super().__init__()
            self.written_files = {}
            self.loop_count = 0

        def call_tool(self, server: str, tool_name: str, args: Dict[str, Any]) -> Any:
            if tool_name == "write_file":
                self.written_files[args["path"]] = args["content"]
                return "File written successfully"
            elif tool_name == "read_file":
                path = args["path"]
                if path in self.written_files:
                    return {"content": self.written_files[path]}
                if path == "docs/01_prd.md":
                    return {"content": "PRD scope"}
                if path == "docs/02_system_design.md":
                    return {
                        "content": (
                            "# System Design Blueprint\n\n"
                            "## 2. API Design\n"
                            "- GET /api/v1/orders (gets status)\n\n"
                            "## 3. Data Models\n"
                            "- User (id, name)\n"
                        )
                    }
                if path == "docs/03_backend_scaffold.md":
                    return {"content": "## Generated File Structure\n- backend/app/api.py\n- backend/app/models.py\n"}
                if path == "docs/04_execution_report.md":
                    return {
                        "content": (
                            "# Runtime Validation Report\n\n"
                            "## 2. Validation Checks\n"
                            "- [x] Configuration Loaded: PASSED\n"
                            "- [x] Python Imports Valid: PASSED\n"
                        )
                    }
                if path == "docs/05_evaluation_report.md":
                    # First run of evaluation: reports missing User entity and order route
                    if self.loop_count == 0:
                        self.loop_count += 1
                        return {
                            "content": (
                                "# Evaluation Report\n\n"
                                "## 1. Summary\n"
                                "- **Overall Score**: 6.0/10.0\n"
                                "- **Status**: FAIL\n\n"
                                "## 3. Issues Detected\n"
                                "- Missing Entity class/schema for 'User' in models.py.\n"
                                "- Missing API endpoint GET /api/v1/orders in api.py.\n"
                            )
                        }
                    else:
                        # Second run of evaluation after repair: PASS
                        return {
                            "content": (
                                "# Evaluation Report\n\n"
                                "## 1. Summary\n"
                                "- **Overall Score**: 10.0/10.0\n"
                                "- **Status**: PASS\n\n"
                                "## 3. Issues Detected\n"
                                "None\n"
                            )
                        }
                return {"content": ""}
            elif tool_name == "execute_command":
                return {
                    "stdout": "VALIDATION_SUCCESS\nCONFIG_LOADED: True\nIMPORTS_VALID: True\n",
                    "stderr": "",
                    "exit_code": 0
                }
            return super().call_tool(server, tool_name, args)

    resolver = LoopIntegrationMockResolver()
    factory = AgentFactory(brain, mcp_resolver=resolver)
    
    # Register agents
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

    conductor = Conductor(brain, factory)
    
    response = conductor.run(
        product_idea="Loop test",
        project_id="proj_loop_1",
        session_id="sess_loop_1"
    )

    assert response["status"] == "success"
    
    # Verify that the repair loop executed and we have the repair decision artifact
    decision_artifact = next((a for a in response["artifacts"] if a["type"] == "repair_decision"), None)
    assert decision_artifact is not None
    assert decision_artifact["file_path"] == "docs/06_repair_decision.json"
    
    data = json.loads(resolver.written_files["docs/06_repair_decision.json"])
    assert data["repair_status"] == "no_action"  # The final loop run results in no action
    assert data["retry_required"] is False
