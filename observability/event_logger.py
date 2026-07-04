from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from brain.database import current_trace_id, current_span_id
from observability.trace_store import TraceStore

class EventLogger:
    def __init__(self, db: Session):
        self.store = TraceStore(db)

    def log(self, event_type: str, payload: Optional[Dict[str, Any]] = None):
        """
        Logs a structured event in the database, bound to the active trace and span if present.
        """
        trace_id = current_trace_id.get()
        span_id = current_span_id.get() or None
        if trace_id:
            self.store.log_event(trace_id, span_id, event_type, payload or {})
