import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from brain.models.postgres_models import Trace, Span, EventLog, MetricSnapshot

logger = logging.getLogger("orchestra_trace_store")

class TraceStore:
    def __init__(self, db: Session):
        self.db = db

    def create_trace(self, trace_id: str, user_id: str, session_id: str) -> Optional[Trace]:
        try:
            trace = Trace(
                id=trace_id,
                user_id=user_id,
                session_id=session_id,
                status="running",
                duration_ms=0,
                created_at=datetime.now(timezone.utc)
            )
            self.db.add(trace)
            self.db.commit()
            self.db.refresh(trace)
            return trace
        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(f"Observability failed to create trace {trace_id}: {e}")
            return None

    def update_trace_status(self, trace_id: str, status: str, duration_ms: int) -> Optional[Trace]:
        try:
            trace = self.db.query(Trace).filter(Trace.id == trace_id).first()
            if trace:
                trace.status = status
                trace.duration_ms = duration_ms
                self.db.commit()
                self.db.refresh(trace)
            return trace
        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(f"Observability failed to update trace {trace_id}: {e}")
            return None

    def create_span(self, span_id: str, trace_id: str, parent_span_id: Optional[str], name: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[Span]:
        try:
            span = Span(
                id=span_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                name=name,
                status="running",
                start_time=datetime.now(timezone.utc),
                metadata_json=metadata or {}
            )
            self.db.add(span)
            self.db.commit()
            self.db.refresh(span)
            return span
        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(f"Observability failed to create span {span_id}: {e}")
            return None

    def close_span(self, span_id: str, status: str = "success", metadata: Optional[Dict[str, Any]] = None) -> Optional[Span]:
        try:
            span = self.db.query(Span).filter(Span.id == span_id).first()
            if span:
                span.status = status
                span.end_time = datetime.now(timezone.utc)
                if metadata:
                    span.metadata_json = {**span.metadata_json, **metadata}
                self.db.commit()
                self.db.refresh(span)
            return span
        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(f"Observability failed to close span {span_id}: {e}")
            return None

    def log_event(self, trace_id: str, span_id: Optional[str], event_type: str, payload: Dict[str, Any]) -> Optional[EventLog]:
        try:
            event = EventLog(
                trace_id=trace_id,
                span_id=span_id,
                event_type=event_type,
                payload_json=payload,
                timestamp=datetime.now(timezone.utc)
            )
            self.db.add(event)
            self.db.commit()
            self.db.refresh(event)
            return event
        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(f"Observability failed to log event {event_type}: {e}")
            return None

    def log_metric(self, trace_id: str, name: str, value: float, unit: str) -> Optional[MetricSnapshot]:
        try:
            metric = MetricSnapshot(
                trace_id=trace_id,
                metric_name=name,
                value=value,
                unit=unit,
                timestamp=datetime.now(timezone.utc)
            )
            self.db.add(metric)
            self.db.commit()
            self.db.refresh(metric)
            return metric
        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(f"Observability failed to log metric {name}: {e}")
            return None

    def get_trace_replay(self, trace_id: str) -> Dict[str, Any]:
        try:
            trace = self.db.query(Trace).filter(Trace.id == trace_id).first()
            if not trace:
                return {}

            spans = self.db.query(Span).filter(Span.trace_id == trace_id).order_by(Span.start_time).all()
            events = self.db.query(EventLog).filter(EventLog.trace_id == trace_id).order_by(EventLog.timestamp).all()
            metrics = self.db.query(MetricSnapshot).filter(MetricSnapshot.trace_id == trace_id).all()

            span_list = []
            for s in spans:
                span_list.append({
                    "id": s.id,
                    "parent_span_id": s.parent_span_id,
                    "name": s.name,
                    "status": s.status,
                    "start_time": s.start_time.isoformat(),
                    "end_time": s.end_time.isoformat() if s.end_time else None,
                    "metadata": s.metadata_json
                })

            event_list = []
            for e in events:
                event_list.append({
                    "id": e.id,
                    "span_id": e.span_id,
                    "event_type": e.event_type,
                    "payload": e.payload_json,
                    "timestamp": e.timestamp.isoformat()
                })

            metric_list = []
            for m in metrics:
                metric_list.append({
                    "metric_name": m.metric_name,
                    "value": m.value,
                    "unit": m.unit,
                    "timestamp": m.timestamp.isoformat()
                })

            return {
                "trace_id": trace.id,
                "session_id": trace.session_id,
                "status": trace.status,
                "duration_ms": trace.duration_ms,
                "spans": span_list,
                "events": event_list,
                "metrics": metric_list
            }
        except Exception as e:
            logger.warning(f"Observability failed to build replay for trace {trace_id}: {e}")
            return {}
