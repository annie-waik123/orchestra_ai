from sqlalchemy.orm import Session
from brain.database import current_trace_id
from observability.trace_store import TraceStore

class MetricsCollector:
    def __init__(self, db: Session):
        self.store = TraceStore(db)

    def record(self, metric_name: str, value: float, unit: str):
        """
        Records a metric snapshot associated with the active trace.
        """
        trace_id = current_trace_id.get()
        if trace_id:
            self.store.log_metric(trace_id, metric_name, value, unit)
        else:
            # Safe ignore if tracer is not initialized
            pass
