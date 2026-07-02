import pytest
from typing import Dict, Any, List, Optional

from agents.models import AgentState
from agents.manifest import AgentManifest
from agents.factory import AgentFactory
from agents.conductor import Conductor
from agents.planning import PlanningAgent
from tests.test_agent_framework import MockBrainServiceClient, MockMcpResolver

def test_conductor_e2e_flow():
    # 1. Initialize mock brain service client and MCP client resolver
    brain = MockBrainServiceClient()
    resolver = MockMcpResolver()
    
    # 2. Register Planning Agent manifest in Project Brain mock registry
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("Planning Agent", PlanningAgent)
    manifest_dict = factory._create_stub_manifest_dict("Planning Agent", ["prd"])
    brain.registered_manifests["Planning Agent"] = manifest_dict
    
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
    
    # 6. Verify that the PlanningAgent successfully stored its outputs in Project Brain
    assert len(response["artifacts"]) == 1
    artifact = response["artifacts"][0]
    assert artifact["type"] == "prd"
    assert artifact["generated_by"] == "Planning Agent"
    assert artifact["file_path"] == "docs/01_prd.md"
    
    # 7. Verify decision record is stored in Project Brain
    assert len(response["decisions"]) == 1
    decision = response["decisions"][0]
    assert decision["agent"] == "Planning Agent"
    assert decision["title"] == "Adopt standard modular workspace"
    
    # 8. Verify the runtime session state adapter reflects Completed status for the node
    state = response["state"]
    assert state["node_planning_node_status"] == "Completed"
    assert state["node_planning_node_outputs"] == ["prd"]
    
    # 9. Verify metrics finalized
    assert "metrics" in response
    assert response["metrics"]["agent_name"] == "Planning Agent"
    assert response["metrics"]["token_usage_prompt"] == 100
    assert response["metrics"]["token_usage_completion"] == 250
