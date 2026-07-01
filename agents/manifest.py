from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class CapabilitiesSpec(BaseModel):
    produces: List[str] = Field(default_factory=list)

class InputSpec(BaseModel):
    artifact_type: str
    required: bool = True

class OutputSpec(BaseModel):
    artifact_type: str
    file_path_pattern: str

class SkillSpec(BaseModel):
    name: str
    min_version: str = "1.0.0"

class RetryPolicy(BaseModel):
    base_delay_seconds: int = 2
    max_retries: int = 3
    exponential_factor: float = 2.0
    escalate_on_exhaustion: bool = True

class EvaluationRules(BaseModel):
    self_check: List[str] = Field(default_factory=list)

class HumanApprovalPolicy(BaseModel):
    trigger_conditions: List[str] = Field(default_factory=list)

class CompatibilitySpec(BaseModel):
    min_framework_version: str = "0.1.0"

class AgentManifest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    schema_version: str = "1.0"
    version: str = "1.0.0"
    name: str
    description: str
    mission: str
    capabilities: CapabilitiesSpec
    inputs: List[InputSpec] = Field(default_factory=list)
    outputs: List[OutputSpec] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    skills: List[SkillSpec] = Field(default_factory=list)
    allowed_mcp_servers: List[str] = Field(default_factory=list)
    preferred_model: str = "gemini-2.5-pro"
    temperature: float = 0.2
    timeout_seconds: int = 300
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    evaluation_rules: EvaluationRules = Field(default_factory=EvaluationRules)
    human_approval_policy: HumanApprovalPolicy = Field(default_factory=HumanApprovalPolicy)
    compatibility: CompatibilitySpec = Field(default_factory=CompatibilitySpec)
