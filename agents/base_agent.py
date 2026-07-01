import time
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Final
from datetime import datetime, timezone

from agents.models import (
    AgentState,
    RetryDecision,
    AgentContext,
    ExecutionPlan,
    RawOutput,
    ArtifactBody,
    DecisionRecord,
    ToolError,
    ConfigurationError,
    TaskTimeoutError,
    ValidationPipelineError,
    ProjectBrainWriteError
)
from agents.manifest import AgentManifest
from agents.tool_manager import ToolManager
from agents.metrics import MetricsCollector
from agents.session_adapter import SessionStateAdapter
from agents.state_machine import AgentStateMachine
from agents.skill_loader import SkillLoader
from agents.brain_client import BrainServiceClient

logger = logging.getLogger("orchestra_agent_framework")

class BaseAgent(ABC):
    """
    Abstract base class for all Orchestra AI specialist agents.
    Encapsulates lifecycle Template Method sequencing, tool manager facade bindings,
    Project Brain transactions, retry loops, and telemetry metrics collection.
    """
    def __init__(
        self,
        manifest: AgentManifest,
        tools: ToolManager,
        metrics: MetricsCollector,
        brain_client: BrainServiceClient,
        session_state: SessionStateAdapter,
        skills_base_dir: Optional[str] = None
    ):
        self.manifest: Final[AgentManifest] = manifest
        self.tools: Final[ToolManager] = tools
        self.metrics: Final[MetricsCollector] = metrics
        self.brain_client: Final[BrainServiceClient] = brain_client
        self.session_state: Final[SessionStateAdapter] = session_state
        self.skills_base_dir: Optional[str] = skills_base_dir

        self.session_id: Optional[str] = None
        self.node_id: Optional[str] = None
        
        self.context: Optional[AgentContext] = None
        self.skills: Dict[str, Any] = {}
        self.state_machine: Optional[AgentStateMachine] = None
        
        self._retries_count: Dict[str, int] = {}
        self.artifacts_body: List[ArtifactBody] = []
        self.plan_obj: Optional[ExecutionPlan] = None

    @property
    def state(self) -> AgentState:
        if self.state_machine:
            return self.state_machine.current_state
        return AgentState.PENDING

    # --- final lifecycle template method ---
    
    def execute_lifecycle(self, session_id: str, node_id: str) -> Dict[str, Any]:
        """
        Fixed ten-phase execution lifecycle sequence (Template Method pattern).
        Ensures consistent transitions, state synchronization, timing, and error handling.
        """
        logger.info(f"Starting execution lifecycle for session {session_id}, node {node_id}")
        
        # Phase 1: initialize (no-retry, setup state machine and toolmanager)
        try:
            self.metrics.record_phase_start("initialize")
            self.session_id = session_id
            self.node_id = node_id
            self.state_machine = AgentStateMachine(self.node_id, self.session_state)
            
            self.initialize(session_id, node_id)
            self.metrics.record_phase_end("initialize")
        except Exception as e:
            self.metrics.record_phase_end("initialize")
            if self.state_machine:
                self.state_machine.transition_to(AgentState.FAILED, f"Initialization failed: {e}")
            self.cleanup()
            self.log_execution()
            raise e

        # Phase 2: retrieve_context (retryable)
        self._run_phase_with_retry(
            phase_name="Retrieving Context",
            metric_name="retrieve_context",
            state_on_start=AgentState.RETRIEVING_CONTEXT,
            state_on_fail=AgentState.FAILED,
            action_callable=lambda: self.retrieve_context()
        )

        # Phase 3 & 4: load_skills & plan (retryable)
        def run_planning():
            self.load_skills()
            self.plan_obj = self.plan(self.context)
            self._validate_plan(self.plan_obj)

        self._run_phase_with_retry(
            phase_name="Planning",
            metric_name="plan",
            state_on_start=AgentState.PLANNING,
            state_on_fail=AgentState.FAILED,
            action_callable=run_planning
        )

        # Phase 5 & 6: execute & generate_artifacts (retryable)
        def run_execution():
            raw = self._execute_with_timeout(self.plan_obj)
            self.artifacts_body = self.generate_artifacts(raw)
            self._process_and_validate_artifacts(self.artifacts_body)

        self._run_phase_with_retry(
            phase_name="Executing",
            metric_name="execute",
            state_on_start=AgentState.EXECUTING,
            state_on_fail=AgentState.FAILED,
            action_callable=run_execution
        )

        # Phase 7: persist_results (non-retryable)
        try:
            self.metrics.record_phase_start("persist_results")
            self.persist_results()
            self.metrics.record_phase_end("persist_results")
            self.state_machine.transition_to(AgentState.COMPLETED, "Completed lifecycle successfully")
        except Exception as e:
            self.metrics.record_phase_end("persist_results")
            self.state_machine.transition_to(AgentState.FAILED, f"Execution failed in Persist Results: {e}")
            self.cleanup()
            self.log_execution()
            raise e
            
        self.cleanup()
        self.log_execution()
        
        return {
            "status": "success",
            "state": self.state.value,
            "metrics": self.metrics.finalize(self.manifest.preferred_model).model_dump()
        }

    def _run_phase_with_retry(
        self,
        phase_name: str,
        metric_name: str,
        state_on_start: AgentState,
        state_on_fail: AgentState,
        action_callable
    ):
        """Helper method encapsulating the phase execution timing and retry logic loops."""
        self.state_machine.transition_to(state_on_start, f"Starting phase: {phase_name}")
        while True:
            try:
                self.metrics.record_phase_start(metric_name)
                action_callable()
                self.metrics.record_phase_end(metric_name)
                break
            except Exception as e:
                self.metrics.record_phase_end(metric_name)
                decision = self.handle_error(e, phase_name)
                if decision == RetryDecision.RETRY:
                    continue
                elif decision == RetryDecision.ESCALATE:
                    raise ValidationPipelineError(f"Human review required for node {self.node_id}: {e}") from e
                else:
                    self.state_machine.transition_to(state_on_fail, f"Execution failed in {phase_name}: {e}")
                    self.cleanup()
                    self.log_execution()
                    raise e

    # --- Core Phase Implementations ---

    def initialize(self, session_id: str, node_id: str):
        """Phase 1: Validates manifests and establishes connections."""
        self.state_machine.transition_to(AgentState.INITIALIZING, "Initializing agent components")
        
        # Check compatibility version
        min_ver = self.manifest.compatibility.min_framework_version
        # Stub version comparison
        if min_ver > "1.0.0":
            raise ConfigurationError(f"Framework version 1.0.0 is incompatible with manifest minimum version {min_ver}")

        # Open ToolManager MCP servers
        self.tools.open()
        
        # Check presence of required inputs
        for input_spec in self.manifest.inputs:
            if input_spec.required:
                present = self.brain_client.check_input_presence(session_id, input_spec.artifact_type)
                if not present:
                    raise ConfigurationError(
                        f"Required input artifact of type '{input_spec.artifact_type}' is missing in session."
                    )

        # Log starting audit record
        self.brain_client.log_audit_action(
            self.session_id,
            self.manifest.name,
            "lifecycle_started",
            {"node_id": self.node_id}
        )

    def retrieve_context(self):
        """Phase 2: Fetches pre-filtered session context block from Context Builder."""
        # Simple local implementation mock / or real Context Builder call.
        # In this interface design, we fetch from a stub client or Context Builder.
        # Let's check context builder availability.
        try:
            # ContextBuilder requires Project Brain endpoints
            # We mock / construct details
            # To be decoupled, retrieve context using project ID and session ID
            # In production, we construct context markdown block
            task_instruction = self.session_state.get_task_instruction(self.node_id)
            
            # Formulate raw markdown block
            self.context = AgentContext(
                decisions=[],
                artifacts=[],
                task_instruction=task_instruction,
                raw_markdown=f"# Task instructions: {task_instruction}",
                context_size_chars=len(task_instruction)
            )
            self.metrics.context_size_chars = self.context.context_size_chars
        except Exception as e:
            raise ToolError("retrieve_context", "brain", f"Context builder failed: {e}", True)

    def load_skills(self):
        """Phase 3: Resolves manifest-declared skill dependencies."""
        loader = SkillLoader(self.skills_base_dir)
        for skill_spec in self.manifest.skills:
            skill = loader.load_skill(skill_spec.name, skill_spec.min_version)
            self.skills[skill_spec.name] = skill

    @abstractmethod
    def plan(self, context: AgentContext) -> ExecutionPlan:
        """Phase 4: Reasoning phase. Returns a structured ExecutionPlan."""
        pass

    @abstractmethod
    def execute(self, plan: ExecutionPlan) -> RawOutput:
        """Phase 5: Task execution phase. Uses self.tools and self.skills."""
        pass

    @abstractmethod
    def generate_artifacts(self, raw: RawOutput) -> List[ArtifactBody]:
        """Phase 6: Artifact transformation phase. Maps RawOutput to ArtifactBody instances."""
        pass

    def persist_results(self):
        """Phase 7: Batch commits artifacts and decisions to Project Brain."""
        self.state_machine.transition_to(AgentState.EXECUTING, "Persisting results to Brain")
        
        # Verify single transactional batch write sequence
        stored_artifacts = []
        try:
            # 1. Write artifacts first
            for ab in self.artifacts_body:
                # Normalize artifact metadata details
                checksum = hashlib.sha256(ab.content.encode("utf-8")).hexdigest()
                
                # Resolve depends_on from active context references matching manifest inputs
                depends_on = []
                for inp_spec in self.manifest.inputs:
                    for art_meta in self.context.artifacts:
                        if art_meta.type == inp_spec.artifact_type:
                            depends_on.append(art_meta.file_path)

                artifact_data = {
                    "session_id": self.session_id,
                    "file_path": ab.file_path,
                    "checksum": checksum,
                    "type": ab.artifact_type,
                    "generated_by": self.manifest.name,
                    "depends_on": list(set(depends_on)),
                    "used_by": []
                }
                
                stored = self.brain_client.store_artifact(artifact_data)
                stored_artifacts.append(stored)
                
            # 2. Write decisions after artifacts succeed
            for ab in self.artifacts_body:
                for dec in ab.decisions:
                    # Decisions with empty rationales are rejected
                    if not dec.rationale or not dec.rationale.strip():
                        raise ProjectBrainWriteError(f"Decision '{dec.title}' rationale is empty.")
                    
                    decision_data = {
                        "session_id": self.session_id,
                        "node": self.node_id,
                        "agent": self.manifest.name,
                        "title": dec.title,
                        "rationale": dec.rationale,
                        "confidence_score": dec.confidence_score,
                        "alternatives_considered": dec.alternatives_considered,
                        "dependencies": [],
                        "artifacts_produced": [ab.file_path]
                    }
                    self.brain_client.store_decision(decision_data)

            # 3. Write audit log
            self.brain_client.log_audit_action(
                self.session_id,
                self.manifest.name,
                "lifecycle_completed",
                {"node_id": self.node_id}
            )

            # Sync node deliverables output to session state adapter
            outputs_list = [a.artifact_type for a in self.manifest.outputs]
            self.session_state.set_node_outputs(self.node_id, outputs_list)
            self.metrics.artifacts_produced = len(stored_artifacts)

        except Exception as e:
            raise ProjectBrainWriteError(f"Batch write failed: {e}") from e

    def cleanup(self):
        """Phase 8: Unconditional resources release."""
        # Unconditionally release tool resources
        try:
            self.tools.close()
        except Exception as e:
            logger.warning(f"Error during ToolManager cleanup close: {e}")
            
        # Clean any uncommitted files (Stub behavior)
        # Finalize metrics enforcers
        self.metrics.finalize(self.manifest.preferred_model)

    def log_execution(self):
        """Phase 9: Structured log emission helper."""
        # Formulates and logs structured trace event details
        record = self.metrics.finalize(self.manifest.preferred_model)
        log_payload = {
            "agent_name": self.manifest.name,
            "session_id": self.session_id,
            "node_id": self.node_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": self.state.value,
            "duration_ms": record.total_execution_ms,
            "token_usage": {
                "prompt": record.token_usage_prompt,
                "completion": record.token_usage_completion
            },
            "cost_usd": record.estimated_cost_usd,
            "retry_count": record.retry_count,
            "history": self.state_machine.history if self.state_machine else []
        }
        logger.info(f"Structured Execution Record: {log_payload}")

    # --- Optional Hook Overrides ---

    def self_evaluate(self, artifacts: List[ArtifactBody]) -> Dict[str, Any]:
        """Optional lightweight specialist check validation hook."""
        return {"passed": True, "failed_rules": []}

    def on_human_review_approved(self, outcome: Dict[str, Any]):
        """Optional hook to react to human review approval instructions."""
        pass

    # --- Internals & Error Helpers ---

    def _execute_with_timeout(self, plan: ExecutionPlan) -> RawOutput:
        # Executes Phase 5 execute method with manifest timeout guard
        start_time = time.time()
        timeout = self.manifest.timeout_seconds
        
        # In a real environment, we'd run in a thread/process with timeout join.
        # For framework completeness, we execute and check wall-clock.
        raw = self.execute(plan)
        
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TaskTimeoutError(f"Execute phase breached timeout threshold of {timeout}s.")
        return raw

    def _validate_plan(self, plan: ExecutionPlan):
        # Validates ExecutionPlan properties against manifest allowed bounds
        if not plan.expected_outputs:
            raise ConfigurationError("ExecutionPlan expected_outputs list cannot be empty.")
            
        # Check required skills
        for skill in plan.required_skills:
            if skill not in [s.name for s in self.manifest.skills]:
                raise ConfigurationError(
                    f"ExecutionPlan requires skill '{skill}' which is not declared in manifest."
                )
                
        # Check required tools
        for tool in plan.required_tools:
            # Resolve tool capability name to backing server
            required_server = self.tools._server_map.get(tool)
            if not required_server or required_server not in self.tools.allowed_servers:
                raise ConfigurationError(
                    f"ExecutionPlan requires capability '{tool}' not allowed by manifest."
                )

        # Topological sort to compute estimated_execution_order
        plan.estimated_execution_order = self._topological_sort_tasks(plan)

    def _topological_sort_tasks(self, plan: ExecutionPlan) -> List[str]:
        # Sorts tasks based on dependencies
        adj = {t.id: [] for t in plan.tasks}
        in_degree = {t.id: 0 for t in plan.tasks}
        
        for dep in plan.dependencies:
            if dep.source in adj and dep.target in adj:
                adj[dep.source].append(dep.target)
                in_degree[dep.target] += 1
                
        # Queue of nodes with 0 in-degree
        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        order = []
        
        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    
        if len(order) < len(plan.tasks):
            # Cycle detected or unresolved dependency, default to plain order
            return [t.id for t in plan.tasks]
        return order

    def _process_and_validate_artifacts(self, artifacts: List[ArtifactBody]):
        if not artifacts:
            raise ValidationPipelineError("No artifacts generated during execution.")
            
        for ab in artifacts:
            # Deterministic linter validation checks
            if ab.artifact_type == "sql_schema":
                res = self.tools.validate_sql(ab.content)
                if not res.get("valid", True):
                    raise ValidationPipelineError(f"SQL validation failed: {res.get('errors')}")
            elif ab.artifact_type == "openapi_spec":
                res = self.tools.validate_openapi(ab.content)
                if not res.get("valid", True):
                    raise ValidationPipelineError(f"OpenAPI validation failed: {res.get('errors')}")
            elif ab.artifact_type == "diagram" or ab.file_path.endswith(".mermaid"):
                res = self.tools.validate_mermaid(ab.content)
                if not res.get("valid", True):
                    raise ValidationPipelineError(f"Mermaid validation failed: {res.get('errors')}")
                    
            # Custom manifest checks
            for check_rule in self.manifest.evaluation_rules.self_check:
                if check_rule == "non-empty" and not ab.content.strip():
                    raise ValidationPipelineError(f"Artifact '{ab.file_path}' content is empty.")
                    
        # Optional self-evaluation checks
        eval_res = self.self_evaluate(artifacts)
        if not eval_res.get("passed", True):
            raise ValidationPipelineError(f"Self-evaluation failed: {eval_res.get('failed_rules')}")

    def handle_error(self, error: Exception, phase: str) -> RetryDecision:
        """Classifies exceptions to determine retry thresholds or escalation logic."""
        logger.error(f"Error encountered in phase '{phase}': {error}")
        self.metrics.record_retry(str(error))
        
        # Decide if error is recoverable
        recoverable = self.is_recoverable(error)
        
        if not recoverable:
            return RetryDecision.FAIL
            
        # Check retry exhaustion
        current_retries = self._retries_count.get(phase, 0)
        max_retries = self.manifest.retry_policy.max_retries
        
        if current_retries < max_retries:
            # Apply backoff delay
            factor = self.manifest.retry_policy.exponential_factor
            delay = self.manifest.retry_policy.base_delay_seconds * (factor ** current_retries)
            logger.info(f"Retrying phase '{phase}' in {delay} seconds (Attempt {current_retries + 1}/{max_retries})")
            
            # Simulate backoff block
            time.sleep(min(delay, 10)) # Cap test delays
            
            self._retries_count[phase] = current_retries + 1
            self.session_state.set_retry_count(self.node_id, current_retries + 1)
            return RetryDecision.RETRY
            
        # Retries exhausted
        if self.manifest.retry_policy.escalate_on_exhaustion:
            self.request_human_review(
                reason=f"Retry exhaustion in phase '{phase}': {error}",
                payload={"error": str(error), "phase": phase}
            )
            return RetryDecision.ESCALATE
            
        return RetryDecision.FAIL

    def is_recoverable(self, error: Exception) -> bool:
        """Classifies error recoverability. Can be overridden by subclasses."""
        # Classify ToolErrors using their hints
        if isinstance(error, ToolError):
            return error.recoverable_hint
        # Timeout and transient network errors are typically recoverable
        err_msg = str(error).lower()
        if "timeout" in err_msg or "rate limit" in err_msg or "429" in err_msg or "connection" in err_msg:
            return True
        return False

    def request_human_review(self, reason: str, payload: Dict[str, Any]):
        """Halts state execution and posts validation reviews to session adapter."""
        self.state_machine.transition_to(AgentState.REVIEW, f"Review requested: {reason}")
        escalation_payload = {
            "node_id": self.node_id,
            "state": self.state.value,
            "reason": reason,
            "details": payload,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.session_state.set_pending_approval(escalation_payload)
