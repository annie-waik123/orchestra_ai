import uuid
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from brain.database import current_trace_id, current_span_id
from observability.trace_store import TraceStore

class SpanManager:
    def __init__(self, db: Session):
        self.store = TraceStore(db)

    def start_span(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        trace_id = current_trace_id.get()
        if not trace_id:
            trace_id = f"tr-fb-{uuid.uuid4().hex[:8]}"
            current_trace_id.set(trace_id)
            self.store.create_trace(trace_id, "test-user-uuid", "fb-sess")

        span_id = f"sp-{uuid.uuid4().hex[:8]}"
        parent_span_id = current_span_id.get() or None

        self.store.create_span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            metadata=metadata
        )
        return span_id

    def finish_span(self, span_id: str, status: str = "success", metadata: Optional[Dict[str, Any]] = None):
        self.store.close_span(span_id, status=status, metadata=metadata)
