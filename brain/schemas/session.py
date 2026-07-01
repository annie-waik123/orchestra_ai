from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

class DAGNode(BaseModel):
    id: str = Field(..., description="Node unique ID")
    name: str = Field(..., description="Logical step name")
    agent: str = Field(..., description="Assigned agent name")
    status: str = Field("PENDING", description="Status (PENDING, RUNNING, COMPLETED, FAILED, RETRYING)")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class DAGEdge(BaseModel):
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")

class DAGHistoryRecord(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    node_id: str
    action: str
    details: Optional[str] = None

class DAGMetadata(BaseModel):
    nodes: List[DAGNode] = Field(default_factory=list)
    edges: List[DAGEdge] = Field(default_factory=list)
    history: List[DAGHistoryRecord] = Field(default_factory=list)

class SessionBase(BaseModel):
    project_id: str
    git_commit_hash: Optional[str] = None

class SessionCreate(SessionBase):
    dag: Optional[DAGMetadata] = None

class SessionUpdate(BaseModel):
    active_node: Optional[str] = None
    status: Optional[str] = None
    git_commit_hash: Optional[str] = None
    dag: Optional[DAGMetadata] = None

class Session(SessionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active_node: Optional[str] = None
    status: str = "IN_PROGRESS"
    dag: DAGMetadata = Field(default_factory=DAGMetadata)
