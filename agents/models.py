from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime

class AgentState(str, Enum):
    PENDING = "Pending"
    INITIALIZING = "Initializing"
    RETRIEVING_CONTEXT = "Retrieving Context"
    PLANNING = "Planning"
    EXECUTING = "Executing"
    REVIEW = "Review"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"

class RetryDecision(str, Enum):
    RETRY = "RETRY"
    FAIL = "FAIL"
    ESCALATE = "ESCALATE"

# Exception Hierarchy
class AgentFrameworkException(Exception):
    """Base exception for all agent framework errors."""
    pass

class ConfigurationError(AgentFrameworkException):
    """Raised when there is a deployment or manifest configuration issue."""
    pass

class TaskTimeoutError(AgentFrameworkException):
    """Raised when execution timeouts are breached."""
    pass

class ValidationPipelineError(AgentFrameworkException):
    """Raised when artifact validation fails."""
    pass

class ProjectBrainWriteError(AgentFrameworkException):
    """Raised when writing metadata or artifacts to Project Brain fails."""
    pass

class ToolError(AgentFrameworkException):
    """Normalized exception wrapper for MCP tool execution failures."""
    def __init__(self, capability: str, server: str, cause: str, recoverable_hint: bool):
        super().__init__(f"Tool capability '{capability}' on server '{server}' failed: {cause}")
        self.capability = capability
        self.server = server
        self.cause = cause
        self.recoverable_hint = recoverable_hint

# Pydantic Schemas

class DecisionRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    title: str = Field(..., description="Short summary of the choice")
    rationale: str = Field(..., description="Rationale for the choice; must be non-empty")
    alternatives_considered: List[str] = Field(default_factory=list)
    confidence_score: float = Field(..., ge=0.0, le=1.0)

    @field_validator("rationale")
    @classmethod
    def validate_rationale_not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Rationale cannot be empty.")
        return value

class ArtifactBody(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    content: str
    artifact_type: str
    file_path: str
    decisions: List[DecisionRecord] = Field(default_factory=list)

class DecisionSummary(BaseModel):
    id: str
    node: str
    agent: str
    title: str
    rationale: str
    confidence_score: float
    alternatives_considered: List[str] = Field(default_factory=list)
    artifacts_produced: List[str] = Field(default_factory=list)

class ArtifactMetadata(BaseModel):
    id: str
    session_id: str
    file_path: str
    version: int
    checksum: str
    type: str
    generated_by: str
    depends_on: List[str] = Field(default_factory=list)
    used_by: List[str] = Field(default_factory=list)

class AgentContext(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    decisions: List[DecisionSummary] = Field(default_factory=list)
    artifacts: List[ArtifactMetadata] = Field(default_factory=list)
    task_instruction: str
    raw_markdown: str
    context_size_chars: int

class Task(BaseModel):
    id: str
    description: str
    capability_required: str

class TaskDependency(BaseModel):
    source: str
    target: str

class ExpectedOutput(BaseModel):
    artifact_type: str
    description: str

class ValidationRule(BaseModel):
    rule_type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

class ExecutionPlan(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    tasks: List[Task] = Field(default_factory=list)
    dependencies: List[TaskDependency] = Field(default_factory=list)
    required_skills: List[str] = Field(default_factory=list)
    required_tools: List[str] = Field(default_factory=list)
    expected_outputs: List[ExpectedOutput] = Field(default_factory=list)
    validation_rules: List[ValidationRule] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    estimated_execution_order: List[str] = Field(default_factory=list)

class RawOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    content_blocks: Dict[str, Any] = Field(default_factory=dict)
    decision_records: List[DecisionRecord] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
