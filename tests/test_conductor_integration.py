import pytest
from typing import Dict, Any, List, Optional

from agents.models import AgentState
from agents.manifest import AgentManifest
from agents.factory import AgentFactory
from agents.session_adapter import SessionStateAdapter
from agents.conductor import Conductor
from agents.planning import PlanningAgent
from agents.blueprint import BlueprintAgent
from agents.implementation import ImplementationAgent
from agents.runtime_validation import RuntimeValidationAgent
from tests.test_agent_framework import MockBrainServiceClient, MockMcpResolver

def test_conductor_e2e_flow():
    # 1. Initialize mock brain service client and MCP client resolver
    brain = MockBrainServiceClient()
    resolver = MockMcpResolver()
    
    # 2. Register Planning Agent, Blueprint Agent, Implementation Agent, and Runtime Validation Agent in Project Brain mock registry
    factory = AgentFactory(brain, mcp_resolver=resolver)
    
    factory.register_agent_class("Planning Agent", PlanningAgent)
    planning_manifest = factory._create_stub_manifest_dict("Planning Agent", ["prd"])
    brain.registered_manifests["Planning Agent"] = planning_manifest
    
    factory.register_agent_class("Blueprint Agent", BlueprintAgent)
    blueprint_manifest = factory._create_stub_manifest_dict("Blueprint Agent", ["blueprint_agent"])
    brain.registered_manifests["Blueprint Agent"] = blueprint_manifest

    factory.register_agent_class("implementation_agent", ImplementationAgent)
    implementation_manifest = factory._create_stub_manifest_dict("implementation_agent", ["implementation_agent"])
    brain.registered_manifests["implementation_agent"] = implementation_manifest

    factory.register_agent_class("runtime_validation_agent", RuntimeValidationAgent)
    validation_manifest = factory._create_stub_manifest_dict("runtime_validation_agent", ["runtime_validation_agent"])
    brain.registered_manifests["runtime_validation_agent"] = validation_manifest
    
    # 3. Instantiate Conductor
    conductor = Conductor(brain_client=brain, agent_factory=factory)
    
    # 4. Execute the Conductor run with a user product idea
    product_idea = "Build a food delivery app for university students"
    response = conductor.run(
        product_idea=product_idea,
        project_id="proj_test_123",
        session_id="sess_test_123"
    )
    
    # 5. Verify the final structured response from Conductor
    assert response["status"] == "success"
    assert response["session_id"] == "sess_test_123"
    assert response["project_id"] == "proj_test_123"
    
    # 6. Verify that the Conductor returns Planning, Blueprint, Implementation, and Validation artifacts
    assert len(response["artifacts"]) == 4
    
    prd_artifact = next(a for a in response["artifacts"] if a["type"] == "prd")
    assert prd_artifact["generated_by"] == "Planning Agent"
    assert prd_artifact["file_path"] == "docs/01_prd.md"
    
    blueprint_artifact = next(a for a in response["artifacts"] if a["type"] == "system_design")
    assert blueprint_artifact["generated_by"] == "Blueprint Agent"
    assert blueprint_artifact["file_path"] == "docs/02_system_design.md"

    scaffold_artifact = next(a for a in response["artifacts"] if a["type"] == "backend_scaffold")
    assert scaffold_artifact["generated_by"] == "implementation_agent"
    assert scaffold_artifact["file_path"] == "docs/03_backend_scaffold.md"

    validation_artifact = next(a for a in response["artifacts"] if a["type"] == "execution_report")
    assert validation_artifact["generated_by"] == "runtime_validation_agent"
    assert validation_artifact["file_path"] == "docs/04_execution_report.md"
    
    # 7. Verify artifact lineage is preserved inside Project Brain
    # Blueprint artifact depends on Planning artifact (docs/01_prd.md)
    assert prd_artifact["file_path"] in blueprint_artifact["depends_on"]
    # Implementation artifact depends on Blueprint artifact (docs/02_system_design.md)
    assert blueprint_artifact["file_path"] in scaffold_artifact["depends_on"]
    # Validation artifact depends on Implementation artifact (docs/03_backend_scaffold.md)
    assert scaffold_artifact["file_path"] in validation_artifact["depends_on"]
    
    # 8. Verify decision records are stored in Project Brain
    assert len(response["decisions"]) == 4
    planning_dec = next(d for d in response["decisions"] if d["agent"] == "Planning Agent")
    assert planning_dec["title"] == "Adopt standard modular workspace"
    
    blueprint_dec = next(d for d in response["decisions"] if d["agent"] == "Blueprint Agent")
    assert blueprint_dec["title"] == "Adopt microservices architecture"

    impl_dec = next(d for d in response["decisions"] if d["agent"] == "implementation_agent")
    assert impl_dec["title"] == "FastAPI project structure mapping rules"

    validation_dec = next(d for d in response["decisions"] if d["agent"] == "runtime_validation_agent")
    assert validation_dec["title"] == "Runtime execution validation in isolated sandbox"
    
    # 9. Verify the runtime session state adapter reflects Completed status for all nodes
    state = response["state"]
    assert state["node_planning_node_status"] == "Completed"
    assert state["node_planning_node_outputs"] == ["prd"]
    
    assert state["node_blueprint_node_status"] == "Completed"
    assert state["node_blueprint_node_outputs"] == ["system_design"]

    assert state["node_implementation_node_status"] == "Completed"
    assert state["node_implementation_node_outputs"] == ["backend_scaffold"]

    assert state["node_validation_node_status"] == "Completed"
    assert state["node_validation_node_outputs"] == ["execution_report"]
    
    # 10. Verify metrics finalized for the final agent (Runtime Validation Agent)
    assert "metrics" in response
    assert response["metrics"]["agent_name"] == "runtime_validation_agent"
    assert response["metrics"]["token_usage_prompt"] == 100
    assert response["metrics"]["token_usage_completion"] == 300


def test_blueprint_agent_output_schema():
    # Verify the specific schema structure of the BlueprintAgent output
    brain = MockBrainServiceClient()
    resolver = MockMcpResolver()
    factory = AgentFactory(brain, mcp_resolver=resolver)
    
    # Register BlueprintAgent
    from agents.blueprint import BlueprintAgent
    factory.register_agent_class("Blueprint Agent", BlueprintAgent)
    
    state_dict = {
        "session_id": "sess_test_123",
        "project_id": "proj_test_123",
        "node_blueprint_node_task_instruction": "Generate system design blueprint based on PRD"
    }
    state_adapter = SessionStateAdapter(state_dict)
    agent = factory.create_by_name("Blueprint Agent", "sess_test_123", "blueprint_node", state_adapter)
    
    # Set up mock PRD in context
    from agents.models import AgentContext, ArtifactMetadata
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(
                id="art-1",
                session_id="sess_test_123",
                file_path="docs/01_prd.md",
                version=1,
                checksum="hash123",
                type="prd",
                generated_by="Planning Agent"
            )
        ],
        task_instruction="Generate system design blueprint based on PRD",
        raw_markdown="# Task",
        context_size_chars=10
    )
    
    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)
    
    assert len(artifacts) == 1
    blueprint_content = artifacts[0].content
    
    # Assert all strict Sprint 3 sections exist
    assert "## 1. System Architecture" in blueprint_content
    assert "## 2. API Design" in blueprint_content
    assert "## 3. Data Models" in blueprint_content
    assert "## 4. Service Decomposition" in blueprint_content
    assert "## 5. Technical Decisions" in blueprint_content
    assert "## 6. Edge Cases and Risks" in blueprint_content


def test_implementation_agent_generation_and_schema():
    # Verify the specific schema structure of the ImplementationAgent output
    brain = MockBrainServiceClient()
    
    class CapturingMcpResolver(MockMcpResolver):
        def __init__(self):
            super().__init__()
            self.written_files = {}

        def call_tool(self, server: str, tool_name: str, args: Dict[str, Any]) -> Any:
            if tool_name == "write_file":
                self.written_files[args["path"]] = args["content"]
                return "File written successfully"
            return super().call_tool(server, tool_name, args)

    resolver = CapturingMcpResolver()
    factory = AgentFactory(brain, mcp_resolver=resolver)
    
    factory.register_agent_class("implementation_agent", ImplementationAgent)
    
    state_dict = {
        "session_id": "sess_test_123",
        "project_id": "proj_test_123",
        "node_implementation_node_task_instruction": "Generate backend code scaffold based on system design blueprint"
    }
    state_adapter = SessionStateAdapter(state_dict)
    agent = factory.create_by_name("implementation_agent", "sess_test_123", "implementation_node", state_adapter)
    
    # Set up mock system design blueprint in context
    from agents.models import AgentContext, ArtifactMetadata
    system_design_content = (
        "# System Design Blueprint\n\n"
        "## 2. API Design\n"
        "- POST /api/v1/orders\n"
        "- GET /api/v1/orders/{id}\n\n"
        "## 3. Data Models\n"
        "- Customer (id, name, email)\n"
        "- Order (id, customer_id, status)\n\n"
        "## 4. Service Decomposition\n"
        "- DeliveryService\n"
    )
    
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(
                id="art-2",
                session_id="sess_test_123",
                file_path="docs/02_system_design.md",
                version=1,
                checksum="hash123",
                type="system_design",
                generated_by="Blueprint Agent"
            )
        ],
        task_instruction="Generate backend code scaffold based on system design blueprint",
        raw_markdown="# Task",
        context_size_chars=10
    )
    
    # Mock reading the system design file from workspace
    resolver.call_tool = lambda server, tool_name, args: (
        {"content": system_design_content} if tool_name == "read_file" else (
            resolver.written_files.update({args["path"]: args["content"]}) or "File written successfully"
            if tool_name == "write_file" else "mocked"
        )
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)
    
    assert len(artifacts) == 1
    scaffold_content = artifacts[0].content
    
    # Assert artifact metadata details
    assert artifacts[0].artifact_type == "backend_scaffold"
    assert artifacts[0].file_path == "docs/03_backend_scaffold.md"
    assert "Backend Scaffold Summary" in scaffold_content
    
    # Verify that the mapped files were written to the workspace via ToolManager
    written_files = resolver.written_files
    assert "backend/.env" in written_files
    assert "backend/app/config.py" in written_files
    assert "backend/app/db.py" in written_files
    assert "backend/app/models.py" in written_files
    assert "backend/app/services.py" in written_files
    assert "backend/app/api.py" in written_files
    assert "backend/app/main.py" in written_files

    # Verify model generation mapped entities properly
    models_code = written_files["backend/app/models.py"]
    assert "class Customer(Base):" in models_code
    assert "class Order(Base):" in models_code
    assert "class CustomerSchema(BaseModel):" in models_code
    assert "class OrderSchema(BaseModel):" in models_code

    # Verify service generation mapped services properly
    services_code = written_files["backend/app/services.py"]
    assert "class DeliveryService:" in services_code

    # Verify api generation mapped routes properly
    api_code = written_files["backend/app/api.py"]
    assert "@router.post('/api/v1/orders')" in api_code
    assert "@router.get('/api/v1/orders/{id}')" in api_code


def test_runtime_validation_agent_direct():
    brain = MockBrainServiceClient()
    
    class ValidationMockResolver(MockMcpResolver):
        def __init__(self):
            super().__init__()
            self.read_calls = []

        def call_tool(self, server: str, tool_name: str, args: Dict[str, Any]) -> Any:
            if tool_name == "read_file":
                path = args["path"]
                self.read_calls.append(path)
                if path == "docs/03_backend_scaffold.md":
                    return {"content": "## Generated File Structure\n- backend/app/main.py\n- backend/app/config.py"}
                return {"content": "mock file content"}
            if tool_name == "execute_command":
                # Simulate real validation tool outputs
                stdout_data = (
                    "VALIDATION_SUCCESS\n"
                    "CONFIG_LOADED: True\n"
                    "IMPORTS_VALID: True\n"
                    "APP_VALID: True\n"
                    "ROUTES_LOADED: True\n"
                    'ROUTES_JSON:[{"path": "/health", "methods": ["GET"]}]'
                )
                return {"stdout": stdout_data, "stderr": "", "exit_code": 0}
            return super().call_tool(server, tool_name, args)

    resolver = ValidationMockResolver()
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("runtime_validation_agent", RuntimeValidationAgent)

    state_dict = {
        "session_id": "sess_val_123",
        "project_id": "proj_val_123",
        "node_validation_node_task_instruction": "Validate backend execution in sandbox"
    }
    state_adapter = SessionStateAdapter(state_dict)
    agent = factory.create_by_name("runtime_validation_agent", "sess_val_123", "validation_node", state_adapter)

    from agents.models import AgentContext, ArtifactMetadata
    agent.context = AgentContext(
        decisions=[],
        artifacts=[
            ArtifactMetadata(
                id="art-3",
                session_id="sess_val_123",
                file_path="docs/03_backend_scaffold.md",
                version=1,
                checksum="hash123",
                type="backend_scaffold",
                generated_by="implementation_agent"
            )
        ],
        task_instruction="Validate backend execution in sandbox",
        raw_markdown="# Task",
        context_size_chars=10
    )

    plan = agent.plan(agent.context)
    agent.tools.open()
    raw = agent.execute(plan)
    artifacts = agent.generate_artifacts(raw)

    assert len(artifacts) == 1
    report = artifacts[0]
    assert report.artifact_type == "execution_report"
    assert report.file_path == "docs/04_execution_report.md"
    assert "**Status**: SUCCESS" in report.content
    assert "Configuration Loaded: PASSED" in report.content
    assert "Python Imports Valid: PASSED" in report.content
    assert "FastAPI App Initialized: PASSED" in report.content
    assert "Routes Loaded: PASSED" in report.content
    assert "`/health`" in report.content

    # Assert only referenced files from scaffold summary were read
    assert "docs/03_backend_scaffold.md" in resolver.read_calls
    assert "backend/app/main.py" in resolver.read_calls
    assert "backend/app/config.py" in resolver.read_calls
    assert len(resolver.read_calls) == 3


