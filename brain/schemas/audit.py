from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from typing import Optional, Dict, Any

class AuditBase(BaseModel):
    session_id: str = Field(..., description="Active session ID")
    agent: str = Field(..., description="Name of the agent or component initiating action")
    action: str = Field(..., description="Type of action (e.g. read_file, run_linter, approve_gate, trigger_loop)")
    details: Optional[Dict[str, Any]] = Field(None, description="Metadata and details of the operation")

class AuditCreate(AuditBase):
    pass

class Audit(AuditBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
