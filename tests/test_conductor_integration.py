import pytest
from typing import Dict, Any, List, Optional

from agents.models import AgentState
from agents.manifest import AgentManifest
from agents.factory import AgentFactory
from agents.session_adapter import SessionStateAdapter
from agents.conductor import Conductor
from agents.planning import PlanningAgent
from agents.blueprint import BlueprintAgent
from tests.test_agent_framework import MockBrainServiceClient, MockMcpResolver

def test_conductor_e2e_flow():
    # 1. Initialize mock brain service client and MCP client resolver
    brain = MockBrainServiceClient()
    resolver = MockMcpResolver()
    
    # 2. Register Planning Agent and Blueprint Agent manifest in Project Brain mock registry
    factory = AgentFactory(brain, mcp_resolver=resolver)
    
    factory.register_agent_class("Planning Agent", PlanningAgent)
    planning_manifest = factory._create_stub_manifest_dict("Planning Agent", ["prd"])
    brain.registered_manifests["Planning Agent"] = planning_manifest
    
    factory.register_agent_class("Blueprint Agent", BlueprintAgent)
    blueprint_manifest = factory._create_stub_manifest_dict("Blueprint Agent", ["blueprint_agent"])
    brain.registered_manifests["Blueprint Agent"] = blueprint_manifest
    
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
    
    # 6. Verify that the Conductor returns both Planning and Blueprint artifacts
    assert len(response["artifacts"]) == 2
    
    prd_artifact = next(a for a in response["artifacts"] if a["type"] == "prd")
    assert prd_artifact["generated_by"] == "Planning Agent"
    assert prd_artifact["file_path"] == "docs/01_prd.md"
    
    blueprint_artifact = next(a for a in response["artifacts"] if a["type"] == "system_design")
    assert blueprint_artifact["generated_by"] == "Blueprint Agent"
    assert blueprint_artifact["file_path"] == "docs/02_system_design.md"
    
    # 7. Verify artifact lineage is preserved inside Project Brain
    # Blueprint artifact depends on Planning artifact (docs/01_prd.md)
    assert prd_artifact["file_path"] in blueprint_artifact["depends_on"]
    
    # 8. Verify decision records are stored in Project Brain
    assert len(response["decisions"]) == 2
    planning_dec = next(d for d in response["decisions"] if d["agent"] == "Planning Agent")
    assert planning_dec["title"] == "Adopt standard modular workspace"
    
    blueprint_dec = next(d for d in response["decisions"] if d["agent"] == "Blueprint Agent")
    assert blueprint_dec["title"] == "Adopt microservices architecture"
    
    # 9. Verify the runtime session state adapter reflects Completed status for both nodes
    state = response["state"]
    assert state["node_planning_node_status"] == "Completed"
    assert state["node_planning_node_outputs"] == ["prd"]
    
    assert state["node_blueprint_node_status"] == "Completed"
    assert state["node_blueprint_node_outputs"] == ["system_design"]
    
    # 10. Verify metrics finalized for the final agent (Blueprint Agent)
    assert "metrics" in response
    assert response["metrics"]["agent_name"] == "Blueprint Agent"
    assert response["metrics"]["token_usage_prompt"] == 150
    assert response["metrics"]["token_usage_completion"] == 450


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
