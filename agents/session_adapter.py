import threading
from typing import Dict, Any, Optional

class SessionStateAdapter:
    """
    Adapter encapsulating read/write integrations with Google ADK session.state.
    Hides raw dictionary structures from BaseAgent.
    Provides thread-safe access to shared session state using RLock.
    """
    def __init__(self, state_dict: Dict[str, Any]):
        self._state = state_dict
        self._lock = threading.RLock()

    def get_session_id(self) -> str:
        with self._lock:
            return self._state.get("session_id", "unknown_session")

    def get_project_id(self) -> str:
        with self._lock:
            return self._state.get("project_id", "unknown_project")

    def get_task_instruction(self, node_id: str) -> str:
        with self._lock:
            return self._state.get(f"node_{node_id}_task_instruction", "")

    def set_node_status(self, node_id: str, status: str):
        with self._lock:
            self._state[f"node_{node_id}_status"] = status

    def set_retry_count(self, node_id: str, retries: int):
        with self._lock:
            self._state[f"node_{node_id}_retry_count"] = retries

    def set_pending_approval(self, payload: Dict[str, Any]):
        with self._lock:
            self._state["pending_approval"] = payload

    def clear_pending_approval(self):
        with self._lock:
            if "pending_approval" in self._state:
                del self._state["pending_approval"]

    def set_node_outputs(self, node_id: str, outputs: list):
        with self._lock:
            self._state[f"node_{node_id}_outputs"] = list(outputs)
