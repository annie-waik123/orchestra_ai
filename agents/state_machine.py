from datetime import datetime, timezone
from typing import List, Dict, Any
from agents.models import AgentState, AgentFrameworkException
from agents.session_adapter import SessionStateAdapter

class AgentStateMachine:
    """
    State machine governing agent transitions.
    Enforces valid states, records timing, and synchronizes node updates in session.state.
    """
    def __init__(self, node_id: str, session_state: SessionStateAdapter):
        self.node_id = node_id
        self.session_state = session_state
        
        self._current_state = AgentState.PENDING
        self.history: List[Dict[str, Any]] = []
        
        # Valid state transition transitions mapping
        # Keys are starting states, values are allowed destination states
        self._allowed_transitions = {
            AgentState.PENDING: [AgentState.INITIALIZING, AgentState.CANCELLED],
            AgentState.INITIALIZING: [AgentState.RETRIEVING_CONTEXT, AgentState.FAILED, AgentState.CANCELLED],
            AgentState.RETRIEVING_CONTEXT: [AgentState.PLANNING, AgentState.EXECUTING, AgentState.CANCELLED],
            AgentState.PLANNING: [AgentState.EXECUTING, AgentState.FAILED, AgentState.CANCELLED],
            AgentState.EXECUTING: [AgentState.COMPLETED, AgentState.REVIEW, AgentState.FAILED, AgentState.CANCELLED],
            AgentState.REVIEW: [AgentState.EXECUTING, AgentState.FAILED, AgentState.CANCELLED],
            AgentState.COMPLETED: [],
            AgentState.FAILED: [],
            AgentState.CANCELLED: []
        }
        
        # Sync initial state to session adapter
        self.session_state.set_node_status(self.node_id, self._current_state.value)

    @property
    def current_state(self) -> AgentState:
        return self._current_state

    def transition_to(self, target_state: AgentState, reason: str = ""):
        if target_state == self._current_state:
            return

        allowed = self._allowed_transitions.get(self._current_state, [])
        # Also allow transition to CANCELLED from any non-terminal state
        # (completed, failed, and cancelled are terminal)
        is_terminal = self._current_state in [AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED]
        
        if target_state not in allowed and not (target_state == AgentState.CANCELLED and not is_terminal):
            raise AgentFrameworkException(
                f"Invalid state transition: Cannot transition from {self._current_state} to {target_state}."
            )

        old_state = self._current_state
        self._current_state = target_state
        
        # Log to transition history
        self.history.append({
            "from_state": old_state.value,
            "to_state": target_state.value,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Sync to adapter
        self.session_state.set_node_status(self.node_id, target_state.value)
