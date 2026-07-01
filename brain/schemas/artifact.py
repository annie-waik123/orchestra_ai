from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from typing import List, Optional

class ArtifactBase(BaseModel):
    session_id: str = Field(..., description="Active session ID")
    file_path: str = Field(..., description="Path to the file relative to workspace root")
    checksum: str = Field(..., description="SHA-256 hash checksum of the file content")
    type: str = Field(..., description="Type of artifact (e.g. prd, sql_schema, openapi_spec, dockerfile, terraform_blueprint)")
    generated_by: str = Field(..., description="The name of the agent or process that created this artifact")
    depends_on: List[str] = Field(default_factory=list, description="List of file paths/artifact IDs this artifact depends on")
    used_by: List[str] = Field(default_factory=list, description="List of agent names/process steps that consume this artifact")

class ArtifactCreate(ArtifactBase):
    pass

class Artifact(ArtifactBase):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique artifact ID (e.g. file_path + version)")
    version: int = Field(1, description="Version number of this file path")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
