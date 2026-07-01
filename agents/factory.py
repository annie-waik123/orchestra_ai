import os
from typing import Dict, Any, Type, Optional, List
from agents.models import ConfigurationError
from agents.manifest import AgentManifest
from agents.base_agent import BaseAgent
from agents.tool_manager import ToolManager
from agents.metrics import MetricsCollector
from agents.session_adapter import SessionStateAdapter
from agents.brain_client import BrainServiceClient

class AgentFactory:
    """
    Factory creating specialist agents. Resolves capability mappings,
    instantiates metrics, scopes ToolManagers, and injects runtime context.
    """
    FRAMEWORK_VERSION = "1.0.0"

    def __init__(self, brain_client: BrainServiceClient, mcp_resolver: Optional[Any] = None, skills_base_dir: Optional[str] = None):
        self.brain_client = brain_client
        self.mcp_resolver = mcp_resolver
        self.skills_base_dir = skills_base_dir
        self.class_registry: Dict[str, Type[BaseAgent]] = {}

    def register_agent_class(self, name: str, agent_class: Type[BaseAgent]):
        """Registers a specialist agent class mapping to a manifest name."""
        self.class_registry[name] = agent_class

    def create_for_capability(self, capability: str, session_id: str, node_id: str, session_state: SessionStateAdapter) -> BaseAgent:
        """Queries manifest by capability outputs, filters, and constructs Agent."""
        manifest_dict = self.brain_client.get_manifest_by_capability(capability)
        if not manifest_dict:
            # Fallback to checking registry keys
            for name, cls in self.class_registry.items():
                # If name matches or matches capability
                if name.lower().replace(" ", "_") == capability.lower().replace(" ", "_"):
                    # Mock/Stub a manifest for testing
                    manifest_dict = self._create_stub_manifest_dict(name, [capability])
                    break
            
            if not manifest_dict:
                raise ConfigurationError(f"No agent registered for capability: {capability}")
            
        manifest = AgentManifest.model_validate(manifest_dict)
        return self.create(manifest, session_id, node_id, session_state)

    def create_by_name(self, name: str, session_id: str, node_id: str, session_state: SessionStateAdapter) -> BaseAgent:
        """Constructs a specific specialist agent by identity name."""
        manifest_dict = self.brain_client.get_agent_manifest(name)
        if not manifest_dict:
            # Fallback: check class registry and construct stub manifest
            if name in self.class_registry:
                manifest_dict = self._create_stub_manifest_dict(name, [])
            else:
                raise ConfigurationError(f"Agent name '{name}' not found in registry.")
                
        manifest = AgentManifest.model_validate(manifest_dict)
        return self.create(manifest, session_id, node_id, session_state)

    def create(self, manifest: AgentManifest, session_id: str, node_id: str, session_state: SessionStateAdapter) -> BaseAgent:
        """Assembles dependencies, validates compatibility, and instantiates agent."""
        # Validate compatibility
        min_ver = manifest.compatibility.min_framework_version
        # Standard semver major check
        try:
            curr_major = int(self.FRAMEWORK_VERSION.split(".")[0])
            min_major = int(min_ver.split(".")[0])
            if curr_major < min_major:
                raise ConfigurationError(
                    f"Agent manifest requires framework version {min_ver}, "
                    f"but running version is {self.FRAMEWORK_VERSION}"
                )
        except (ValueError, IndexError):
            if min_ver > self.FRAMEWORK_VERSION:
                raise ConfigurationError(f"Incompatible framework version: {self.FRAMEWORK_VERSION} < {min_ver}")

        # Resolve agent class
        cls = self.class_registry.get(manifest.name)
        if not cls:
            raise ConfigurationError(f"No class implementation registered for agent name: {manifest.name}")

        # Construct helper dependencies
        metrics = MetricsCollector(manifest.name, session_id, node_id)
        tools = ToolManager(manifest.allowed_mcp_servers, metrics, self.mcp_resolver)

        # Instantiate agent
        agent = cls(
            manifest=manifest,
            tools=tools,
            metrics=metrics,
            brain_client=self.brain_client,
            session_state=session_state,
            skills_base_dir=self.skills_base_dir
        )
        return agent

    def _create_stub_manifest_dict(self, name: str, capabilities: List[str]) -> Dict[str, Any]:
        return {
            "schema_version": "1.0",
            "version": "1.0.0",
            "name": name,
            "description": f"Stub manifest for {name}",
            "mission": f"Execute tasks for {name}",
            "capabilities": {"produces": capabilities},
            "inputs": [],
            "outputs": [{"artifact_type": c, "file_path_pattern": f"{c}.md"} for c in capabilities],
            "allowed_mcp_servers": ["filesystem", "sandbox", "developer_knowledge"],
            "retry_policy": {
                "base_delay_seconds": 1,
                "max_retries": 2,
                "exponential_factor": 1.5,
                "escalate_on_exhaustion": True
            },
            "compatibility": {
                "min_framework_version": "1.0.0"
            }
        }
