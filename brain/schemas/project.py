from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from typing import Optional

class ProjectBase(BaseModel):
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Detailed description")

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique project ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    status: str = Field("active", description="Project status (active, completed, archived)")
