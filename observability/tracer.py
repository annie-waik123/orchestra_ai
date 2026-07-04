import uuid
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from brain.database import current_trace_id, current_span_id
from observability.trace_store import TraceStore

class Tracer:
    def __init__(self, db: Session):
        self.store = TraceStore(db)

    def start_trace(self, user_id: str, session_id: str, trace_id: Optional[str] = None) -> str:
        tid = trace_id or f"tr-{uuid.uuid4().hex[:8]}"
        current_trace_id.set(tid)
        self.store.create_trace(tid, user_id, session_id)
        return tid

    def end_trace(self, trace_id: str, status: str, duration_ms: int):
        self.store.update_trace_status(trace_id, status, duration_ms)

class SpanContext:
    def __init__(self, db: Session, name: str, metadata: Optional[Dict[str, Any]] = None):
        self.db = db
        self.store = TraceStore(db)
        self.name = name
        self.metadata = metadata or {}
        self.span_id = f"sp-{uuid.uuid4().hex[:8]}"
        self.parent_token = None
        self.trace_id = current_trace_id.get()

    def __enter__(self):
        if not self.trace_id:
            # Fallback for isolated scripts/tests
            self.trace_id = f"tr-fb-{uuid.uuid4().hex[:8]}"
            current_trace_id.set(self.trace_id)
            self.store.create_trace(self.trace_id, "test-user-uuid", "fb-sess")

        self.parent_span_id = current_span_id.get() or None
        self.parent_token = current_span_id.set(self.span_id)

        self.store.create_span(
            span_id=self.span_id,
            trace_id=self.trace_id,
            parent_span_id=self.parent_span_id,
            name=self.name,
            metadata=self.metadata
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "success"
        meta = self.metadata or {}
        if exc_type is not None:
            status = "failed"
            meta["error"] = f"{exc_type.__name__}: {str(exc_val)}"

        self.store.close_span(self.span_id, status=status, metadata=meta)
        if self.parent_token:
            current_span_id.reset(self.parent_token)
