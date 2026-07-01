import time
import math
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class MetricsRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    agent_name: str
    session_id: str
    node_id: str
    token_usage_prompt: int = 0
    token_usage_completion: int = 0
    prompt_size_chars: List[int] = Field(default_factory=list)
    context_size_chars: int = 0
    output_size_chars: int = 0
    tool_latency_p50_ms: float = 0.0
    tool_latency_p99_ms: float = 0.0
    model_latency_total_ms: float = 0.0
    total_execution_ms: float = 0.0
    retry_count: int = 0
    estimated_cost_usd: float = 0.0
    artifacts_produced: int = 0

class MetricsCollector:
    """
    Collects execution telemetry and computes aggregate performance,
    latency percentiles, cost models, and token growth metrics.
    """
    def __init__(self, agent_name: str, session_id: str, node_id: str):
        self.agent_name = agent_name
        self.session_id = session_id
        self.node_id = node_id
        
        self._start_time: float = time.time()
        self._phase_starts: Dict[str, float] = {}
        self.phase_durations: Dict[str, float] = {}
        
        self.token_usage_prompt: int = 0
        self.token_usage_completion: int = 0
        self.prompt_size_chars: List[int] = []
        self.context_size_chars: int = 0
        self.output_size_chars: int = 0
        
        self.tool_calls: List[Dict[str, Any]] = []
        self.model_calls: List[Dict[str, Any]] = []
        self.retries: List[str] = []
        self.artifacts_produced: int = 0
        
        # Simple Pricing Table (USD per 1M tokens)
        self._pricing_table = {
            "gemini-2.5-pro": {"prompt": 1.25, "completion": 3.75},
            "gemini-2.5-flash": {"prompt": 0.075, "completion": 0.30},
            "gemini-3.5-pro": {"prompt": 1.25, "completion": 3.75},
            "gemini-3.5-flash": {"prompt": 0.075, "completion": 0.30},
        }

    def record_phase_start(self, phase: str):
        self._phase_starts[phase] = time.time()

    def record_phase_end(self, phase: str):
        if phase in self._phase_starts:
            duration = (time.time() - self._phase_starts[phase]) * 1000.0
            self.phase_durations[phase] = self.phase_durations.get(phase, 0.0) + duration

    def record_model_call(self, tokens_in: int, tokens_out: int, latency_ms: float, prompt_chars: Optional[int] = None):
        self.token_usage_prompt += tokens_in
        self.token_usage_completion += tokens_out
        self.model_calls.append({
            "prompt_tokens": tokens_in,
            "completion_tokens": tokens_out,
            "latency_ms": latency_ms
        })
        if prompt_chars is not None:
            self.prompt_size_chars.append(prompt_chars)

    def record_tool_call(self, capability: str, latency_ms: float, success: bool):
        self.tool_calls.append({
            "capability": capability,
            "latency_ms": latency_ms,
            "success": success
        })

    def record_retry(self, reason: str):
        self.retries.append(reason)

    def calculate_percentile(self, values: List[float], percentile: float) -> float:
        if not values:
            return 0.0
        sorted_val = sorted(values)
        k = (len(sorted_val) - 1) * (percentile / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_val[int(k)]
        d0 = sorted_val[int(f)] * (c - k)
        d1 = sorted_val[int(c)] * (k - f)
        return d0 + d1

    def finalize(self, preferred_model: str = "gemini-2.5-pro") -> MetricsRecord:
        total_ms = (time.time() - self._start_time) * 1000.0
        
        tool_latencies = [t["latency_ms"] for t in self.tool_calls]
        p50 = self.calculate_percentile(tool_latencies, 50.0)
        p99 = self.calculate_percentile(tool_latencies, 99.0)
        
        model_latency_total = sum(m["latency_ms"] for m in self.model_calls)
        
        # Calculate pricing estimation
        pricing = self._pricing_table.get(preferred_model.lower(), self._pricing_table["gemini-2.5-pro"])
        cost = (
            (self.token_usage_prompt / 1000000.0) * pricing["prompt"] +
            (self.token_usage_completion / 1000000.0) * pricing["completion"]
        )
        
        return MetricsRecord(
            agent_name=self.agent_name,
            session_id=self.session_id,
            node_id=self.node_id,
            token_usage_prompt=self.token_usage_prompt,
            token_usage_completion=self.token_usage_completion,
            prompt_size_chars=self.prompt_size_chars,
            context_size_chars=self.context_size_chars,
            output_size_chars=self.output_size_chars,
            tool_latency_p50_ms=p50,
            tool_latency_p99_ms=p99,
            model_latency_total_ms=model_latency_total,
            total_execution_ms=total_ms,
            retry_count=len(self.retries),
            estimated_cost_usd=cost,
            artifacts_produced=self.artifacts_produced
        )
