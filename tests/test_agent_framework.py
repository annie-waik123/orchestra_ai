import pytest
from typing import Dict, Any, List, Optional
from datetime import datetime

from agents.models import (
    AgentState,
    RetryDecision,
    AgentFrameworkException,
    ConfigurationError,
    TaskTimeoutError,
    ValidationPipelineError,
    ProjectBrainWriteError,
    ToolError,
    DecisionRecord,
    ArtifactBody,
    AgentContext,
    ExecutionPlan,
    RawOutput
)
from agents.manifest import AgentManifest
from agents.base_agent import BaseAgent
from agents.tool_manager import ToolManager
from agents.metrics import MetricsCollector, MetricsRecord
from agents.session_adapter import SessionStateAdapter
from agents.state_machine import AgentStateMachine
from agents.skill_loader import SkillLoader, Skill
from agents.brain_client import BrainServiceClient
from agents.factory import AgentFactory
from agents.planning import PlanningAgent

# --- Mock Implementations ---

class MockBrainServiceClient(BrainServiceClient):
    def __init__(self):
        self.artifacts = {}
        self.decisions = []
        self.audits = []
        self.registered_manifests = {}
        self.input_presence_dict = {}

    def store_artifact(self, artifact_data: Dict[str, Any]) -> Dict[str, Any]:
        art_id = f"art-{len(self.artifacts) + 1}"
        stored = {**artifact_data, "id": art_id, "version": 1}
        self.artifacts[art_id] = stored
        return stored

    def store_decision(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        dec_id = f"dec-{len(self.decisions) + 1}"
        stored = {**decision_data, "id": dec_id}
        self.decisions.append(stored)
        return stored

    def log_audit_action(
        self, 
        session_id: str, 
        agent: str, 
        action: str, 
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        aud_id = f"aud-{len(self.audits) + 1}"
        stored = {
            "id": aud_id,
            "session_id": session_id,
            "agent": agent,
            "action": action,
            "details": details or {}
        }
        self.audits.append(stored)
        return stored

    def check_input_presence(self, session_id: str, artifact_type: str) -> bool:
        return self.input_presence_dict.get((session_id, artifact_type), True)

    def get_agent_manifest(self, name: str) -> Optional[Dict[str, Any]]:
        return self.registered_manifests.get(name)

    def get_manifest_by_capability(self, capability: str) -> Optional[Dict[str, Any]]:
        for m in self.registered_manifests.values():
            if capability in m.get("capabilities", {}).get("produces", []):
                return m
        return None

class MockMcpResolver:
    def __init__(self):
        self.call_count = 0
        self.should_fail_transient = False
        self.should_fail_critical = False
        
    def call_tool(self, server: str, tool_name: str, args: Dict[str, Any]) -> Any:
        self.call_count += 1
        if self.should_fail_transient:
            raise Exception("Timeout connecting to server / transient busy")
        if self.should_fail_critical:
            raise Exception("Undeclared capabilities or linter syntax errors")
            
        # Simulate linter returns
        if tool_name in ["lint_sql", "lint_openapi", "lint_mermaid"]:
            return {"valid": True, "errors": []}
        if tool_name == "query_knowledge":
            return [{"excerpt": "Grounding details reference info"}]
        if tool_name == "read_file":
            return {"content": "workspace mock file info"}
        return f"Mocked tool result: {server}/{tool_name}"

# --- Test Cases ---

def test_state_machine():
    state_dict = {}
    adapter = SessionStateAdapter(state_dict)
    sm = AgentStateMachine("test_node", adapter)
    
    assert sm.current_state == AgentState.PENDING
    assert state_dict["node_test_node_status"] == "Pending"
    
    # Valid transitions
    sm.transition_to(AgentState.INITIALIZING, "Initializing components")
    assert sm.current_state == AgentState.INITIALIZING
    assert state_dict["node_test_node_status"] == "Initializing"
    
    sm.transition_to(AgentState.RETRIEVING_CONTEXT, "Retrieving details")
    assert sm.current_state == AgentState.RETRIEVING_CONTEXT
    
    sm.transition_to(AgentState.PLANNING, "Scoping work")
    assert sm.current_state == AgentState.PLANNING
    
    sm.transition_to(AgentState.EXECUTING, "Doing execution")
    assert sm.current_state == AgentState.EXECUTING
    
    sm.transition_to(AgentState.COMPLETED, "Success")
    assert sm.current_state == AgentState.COMPLETED
    
    # Invalid transitions should throw exceptions
    with pytest.raises(AgentFrameworkException):
        sm.transition_to(AgentState.EXECUTING, "Cannot go backward from terminal state")

def test_tool_manager_allowed_servers():
    metrics = MetricsCollector("TestAgent", "sess_1", "node_1")
    resolver = MockMcpResolver()
    
    # Declare tool manager with only filesystem allowed
    tm = ToolManager(allowed_mcp_servers=["filesystem"], metrics=metrics, mcp_client_resolver=resolver)
    tm.open()
    
    # Allowed call
    res = tm.read_workspace_file("test.txt")
    assert "workspace mock" in res
    assert resolver.call_count == 1
    
    # Disallowed call should throw ConfigurationError
    with pytest.raises(ConfigurationError):
        tm.validate_sql("SELECT * FROM users")

def test_tool_manager_error_normalization():
    metrics = MetricsCollector("TestAgent", "sess_1", "node_1")
    resolver = MockMcpResolver()
    resolver.should_fail_transient = True
    
    tm = ToolManager(allowed_mcp_servers=["filesystem"], metrics=metrics, mcp_client_resolver=resolver)
    tm.open()
    
    with pytest.raises(ToolError) as exc_info:
        tm.read_workspace_file("test.txt")
        
    assert exc_info.value.capability == "read_workspace_file"
    assert exc_info.value.server == "filesystem"
    assert exc_info.value.recoverable_hint is True # transient text maps to recoverable

def test_agent_factory_compatibility():
    brain = MockBrainServiceClient()
    factory = AgentFactory(brain)
    
    # Construct manifest asking for higher framework version than 1.0.0
    manifest = AgentManifest(
        name="PlanningAgent",
        description="Scoping specialist",
        mission="Complete scope plans",
        capabilities={"produces": ["prd"]},
        compatibility={"min_framework_version": "2.0.0"} # incompatible!
    )
    
    factory.register_agent_class("PlanningAgent", PlanningAgent)
    state_adapter = SessionStateAdapter({})
    
    with pytest.raises(ConfigurationError) as exc_info:
        factory.create(manifest, "sess_1", "node_1", state_adapter)
        
    assert "requires framework version" in str(exc_info.value)

def test_base_agent_lifecycle_success():
    brain = MockBrainServiceClient()
    resolver = MockMcpResolver()
    
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("Planning Agent", PlanningAgent)
    
    manifest_dict = factory._create_stub_manifest_dict("Planning Agent", ["prd"])
    brain.registered_manifests["Planning Agent"] = manifest_dict
    
    state_dict = {
        "session_id": "sess_123",
        "project_id": "proj_123",
        "node_planning_node_task_instruction": "Scaffolding rental property app scope"
    }
    state_adapter = SessionStateAdapter(state_dict)
    
    agent = factory.create_by_name("Planning Agent", "sess_123", "planning_node", state_adapter)
    assert isinstance(agent, PlanningAgent)
    
    res = agent.execute_lifecycle("sess_123", "planning_node")
    
    assert res["status"] == "success"
    assert agent.state == AgentState.COMPLETED
    assert state_dict["node_planning_node_status"] == "Completed"
    
    # Check Brain Persist transactions
    assert len(brain.artifacts) == 1
    assert len(brain.decisions) == 1
    assert len(brain.audits) == 2 # 1 inside execute_lifecycle state logging + 1 explicit completed audit
    
    # Verify outputs populated in session state
    assert state_dict["node_planning_node_outputs"] == ["prd"]

def test_base_agent_lifecycle_retry_transient():
    brain = MockBrainServiceClient()
    resolver = MockMcpResolver()
    resolver.should_fail_transient = True # fail tool calls transiently first
    
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("Planning Agent", PlanningAgent)
    
    manifest_dict = factory._create_stub_manifest_dict("Planning Agent", ["prd"])
    manifest_dict["retry_policy"] = {
        "base_delay_seconds": 0, # instant retries for test speed
        "max_retries": 2,
        "exponential_factor": 1.0,
        "escalate_on_exhaustion": False
    }
    brain.registered_manifests["Planning Agent"] = manifest_dict
    
    state_dict = {
        "session_id": "sess_123",
        "project_id": "proj_123",
        "node_planning_node_task_instruction": "Scaffolding rental property app scope"
    }
    state_adapter = SessionStateAdapter(state_dict)
    agent = factory.create_by_name("Planning Agent", "sess_123", "planning_node", state_adapter)
    
    # To test recovery, let's toggle the mock to succeed after 1 failure
    original_call_tool = resolver.call_tool
    def recovery_call_tool(server: str, tool_name: str, args: Dict[str, Any]) -> Any:
        if resolver.should_fail_transient:
            resolver.should_fail_transient = False # clear error so subsequent attempts succeed
            raise Exception("Timeout connecting to server / transient busy")
        return original_call_tool(server, tool_name, args)
    
    resolver.call_tool = recovery_call_tool
    
    res = agent.execute_lifecycle("sess_123", "planning_node")
    
    assert res["status"] == "success"
    assert agent.state == AgentState.COMPLETED
    # Verify retry counters updated in adapter
    assert state_dict["node_planning_node_retry_count"] == 1

def test_base_agent_lifecycle_critical_fail():
    brain = MockBrainServiceClient()
    resolver = MockMcpResolver()
    resolver.should_fail_critical = True # fail tool calls critically
    
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("Planning Agent", PlanningAgent)
    
    manifest_dict = factory._create_stub_manifest_dict("Planning Agent", ["prd"])
    brain.registered_manifests["Planning Agent"] = manifest_dict
    
    state_dict = {
        "session_id": "sess_123",
        "project_id": "proj_123",
        "node_planning_node_task_instruction": "Scaffolding rental property app scope"
    }
    state_adapter = SessionStateAdapter(state_dict)
    agent = factory.create_by_name("Planning Agent", "sess_123", "planning_node", state_adapter)
    
    # Critical failures transition to FAILED immediately
    with pytest.raises(ToolError):
        agent.execute_lifecycle("sess_123", "planning_node")
        
    assert agent.state == AgentState.FAILED
    assert state_dict["node_planning_node_status"] == "Failed"

def test_base_agent_lifecycle_escalate_to_review():
    brain = MockBrainServiceClient()
    resolver = MockMcpResolver()
    resolver.should_fail_transient = True # fail consistently
    
    factory = AgentFactory(brain, mcp_resolver=resolver)
    factory.register_agent_class("Planning Agent", PlanningAgent)
    
    manifest_dict = factory._create_stub_manifest_dict("Planning Agent", ["prd"])
    manifest_dict["retry_policy"] = {
        "base_delay_seconds": 0,
        "max_retries": 1,
        "exponential_factor": 1.0,
        "escalate_on_exhaustion": True # Escalate to Human review on exhaust
    }
    brain.registered_manifests["Planning Agent"] = manifest_dict
    
    state_dict = {
        "session_id": "sess_123",
        "project_id": "proj_123",
        "node_planning_node_task_instruction": "Scaffolding rental property app scope"
    }
    state_adapter = SessionStateAdapter(state_dict)
    agent = factory.create_by_name("Planning Agent", "sess_123", "planning_node", state_adapter)
    
    with pytest.raises(ValidationPipelineError) as exc_info:
        agent.execute_lifecycle("sess_123", "planning_node")
        
    assert "Human review required" in str(exc_info.value)
    assert agent.state == AgentState.REVIEW
    assert state_dict["node_planning_node_status"] == "Review"
    assert "pending_approval" in state_dict
    assert state_dict["pending_approval"]["node_id"] == "planning_node"

def test_metrics_collector_accumulation():
    import time
    metrics = MetricsCollector("TestAgent", "sess_1", "node_1")
    
    metrics.record_phase_start("test_phase")
    time.sleep(0.01) # 10ms
    metrics.record_phase_end("test_phase")
    first_duration = metrics.phase_durations["test_phase"]
    assert first_duration >= 10.0
    
    metrics.record_phase_start("test_phase")
    time.sleep(0.01) # another 10ms
    metrics.record_phase_end("test_phase")
    second_duration = metrics.phase_durations["test_phase"]
    
    # Assert accumulation occurred
    assert second_duration > first_duration
    assert second_duration >= 20.0

def test_session_adapter_thread_safety():
    import threading
    state_dict = {}
    adapter = SessionStateAdapter(state_dict)
    
    def run_updates(thread_idx):
        for i in range(50):
            adapter.set_node_status(f"node_{thread_idx}_{i}", f"status_{i}")
            adapter.set_retry_count(f"node_{thread_idx}_{i}", i)
            adapter.set_node_outputs(f"node_{thread_idx}_{i}", [f"output_{i}"])
            
    threads = []
    for idx in range(10):
        t = threading.Thread(target=run_updates, args=(idx,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    # Verify no exceptions thrown and states populated
    assert state_dict["node_node_0_49_status"] == "status_49"
    assert state_dict["node_node_9_49_retry_count"] == 49

