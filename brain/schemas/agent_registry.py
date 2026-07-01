from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from typing import List, Optional

class AgentRegistryBase(BaseModel):
    name: str = Field(..., description="Unique agent identifier (e.g. Planning Agent)")
    description: str = Field(..., description="Details of the agent's role")
    status: str = Field("active", description="Status (active, inactive)")
    system_prompt: str = Field(..., description="Core system instructions configuration")
    inputs: List[str] = Field(default_factory=list, description="List of expected inputs/context keys")
    outputs: List[str] = Field(default_factory=list, description="List of deliverables or outputs generated")
    skills: List[str] = Field(default_factory=list, description="Skills this agent possesses")
    mcp_servers: List[str] = Field(default_factory=list, description="Required MCP servers to bind at runtime")

class AgentRegistryCreate(AgentRegistryBase):
    pass

class AgentRegistry(AgentRegistryBase):
    model_config = ConfigDict(from_attributes=True)

    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
