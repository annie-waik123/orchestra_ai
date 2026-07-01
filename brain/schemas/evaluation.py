from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

class EvaluationMetric(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0, description="Metric score normalized between 0.0 and 1.0")
    details: Optional[str] = Field(None, description="Explanation or logs for the specific score")

class EvaluationCreate(BaseModel):
    session_id: str = Field(..., description="Active session ID")
    completeness: EvaluationMetric = Field(..., description="Metric for present artifacts")
    consistency: EvaluationMetric = Field(..., description="Metric for schema and route consistency")
    security: EvaluationMetric = Field(..., description="Metric for threat models and vulnerabilities")
    documentation_quality: EvaluationMetric = Field(..., description="Metric for mermaid and markdown sanity")
    deployability: EvaluationMetric = Field(..., description="Metric for container and IaC validity")
    composite_score: float = Field(..., ge=0.0, le=10.0, description="Weighted composite score out of 10")
    passed: bool = Field(..., description="True if composite_score >= threshold and security checks clear")
    logs: List[str] = Field(default_factory=list, description="General evaluation step trace logs")
    findings: List[Dict[str, Any]] = Field(default_factory=list, description="Audit defects list")

class Evaluation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completeness: EvaluationMetric
    consistency: EvaluationMetric
    security: EvaluationMetric
    documentation_quality: EvaluationMetric
    deployability: EvaluationMetric
    composite_score: float
    passed: bool
    logs: List[str]
    findings: List[Dict[str, Any]]
