from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Name of the project")
    description: Optional[str] = Field(None, description="Optional description of the project")

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: str
    status: str

class RunProjectRequest(BaseModel):
    product_idea: str = Field(..., min_length=1, description="The product idea / business requirement prompt")

class RunProjectResponse(BaseModel):
    project_id: str
    session_id: str
    job_id: str
    status: str

class ProjectStatusResponse(BaseModel):
    project_id: str
    session_id: Optional[str] = None
    status: str
    active_stage: Optional[str] = None
    progress: float
    node_states: Dict[str, str] = Field(default_factory=dict)

class ArtifactResponse(BaseModel):
    id: str
    session_id: str
    file_path: str
    version: int
    checksum: str
    type: str
    generated_by: str
    depends_on: List[str] = Field(default_factory=list)
    used_by: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None

class SessionResponse(BaseModel):
    id: str
    project_id: str
    status: str
    created_at: str
    active_node: Optional[str] = None
    git_commit_hash: Optional[str] = None

class LogResponse(BaseModel):
    project_id: str
    session_id: Optional[str] = None
    audit_logs: List[Dict[str, Any]] = Field(default_factory=list)
    execution_logs: str

class ErrorResponse(BaseModel):
    detail: str
