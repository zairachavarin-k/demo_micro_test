"""
Distributed tracing instrumentation for correlation and dependency analysis.

This module provides structured logging with W3C trace context for:
  • Trace ID, Span ID correlation across service boundaries
  • Request/dependency timing and result codes
  • Exception and retry tracking
  • Azure Application Insights integration

Usage:
    from tracer import get_tracer
    
    tracer = get_tracer(__name__)
    with tracer.trace_request("GET /transactions") as span:
        # Your code here
        span.add_tag("pool_acquired_ms", acquisition_time)
        span.add_tag("query_execution_ms", execution_time)
"""

import json
import logging
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class TraceSpan:
    """Represents a single span in a distributed trace."""
    
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time_ms: float
    end_time_ms: Optional[float]
    status_code: Optional[int]
    duration_ms: Optional[float]
    tags: Dict[str, Any]
    exception: Optional[str]
    
    def to_dict(self) -> Dict:
        """Convert span to dictionary for JSON serialization."""
        return {
            k: v for k, v in asdict(self).items()
            if v is not None
        }


class TracingContext:
    """Thread-local tracing context for W3C trace context."""
    
    def __init__(self):
        self.trace_id = str(uuid.uuid4()).replace("-", "")[:16]
        self.parent_span_id = None
        self.spans = []
    
    def new_span(self, span_id: str) -> str:
        """Create new span with current trace ID."""
        return self.trace_id, span_id, self.parent_span_id


class Tracer:
    """Distributed tracer for correlation and telemetry."""
    
    def __init__(self, component_name: str):
        self.component_name = component_name
        self.logger = logging.getLogger(component_name)
        self.context = TracingContext()
    
    def _new_span_id(self) -> str:
        return str(uuid.uuid4()).replace("-", "")[:8]
    
    @contextmanager
    def trace_request(
        self,
        operation_name: str,
        status_code: Optional[int] = None,
    ):
        """Context manager for tracing a request with timing and result."""
        span_id = self._new_span_id()
        trace_id, _, parent_span_id = self.context.new_span(span_id)
        
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            start_time_ms=time.time() * 1000,
            end_time_ms=None,
            status_code=status_code,
            duration_ms=None,
            tags={},
            exception=None,
        )
        
        old_parent = self.context.parent_span_id
        self.context.parent_span_id = span_id
        
        try:
            yield span
        except Exception as e:
            span.exception = traceback.format_exc()
            raise
        finally:
            span.end_time_ms = time.time() * 1000
            span.duration_ms = span.end_time_ms - span.start_time_ms
            
            self.logger.info(
                f"TRACE {span.trace_id} {operation_name}",
                extra={
                    "trace_id": span.trace_id,
                    "span_id": span.span_id,
                    "duration_ms": span.duration_ms,
                    "status_code": span.status_code,
                    "tags": span.tags,
                    "exception": span.exception,
                },
            )
            
            self.context.spans.append(span)
            self.context.parent_span_id = old_parent
    
    @contextmanager
    def trace_dependency(
        self,
        dependency_name: str,
        dependency_type: str = "database",
    ):
        """Context manager for tracing a dependency call."""
        span = TraceSpan(
            trace_id=self.context.trace_id,
            span_id=self._new_span_id(),
            parent_span_id=self.context.parent_span_id,
            operation_name=f"{dependency_type}/{dependency_name}",
            start_time_ms=time.time() * 1000,
            end_time_ms=None,
            status_code=None,
            duration_ms=None,
            tags={
                "dependency_type": dependency_type,
                "dependency_name": dependency_name,
            },
            exception=None,
        )
        
        try:
            yield span
        except Exception as e:
            span.exception = str(e)
            raise
        finally:
            span.end_time_ms = time.time() * 1000
            span.duration_ms = span.end_time_ms - span.start_time_ms
            self.context.spans.append(span)
    
    def get_trace_headers(self) -> Dict[str, str]:
        """Get W3C trace context headers for propagation."""
        return {
            "traceparent": (
                f"00-{self.context.trace_id}-"
                f"{self.context.parent_span_id or self._new_span_id()}-01"
            ),
        }
    
    def export_spans(self) -> str:
        """Export collected spans as JSON for Application Insights."""
        return json.dumps(
            [span.to_dict() for span in self.context.spans],
            indent=2,
        )


# Global tracer registry
_tracers: Dict[str, Tracer] = {}


def get_tracer(component_name: str) -> Tracer:
    """Get or create a tracer for a component."""
    if component_name not in _tracers:
        _tracers[component_name] = Tracer(component_name)
    return _tracers[component_name]


# Configure logging to output JSON for Application Insights
def configure_tracing_logging():
    """Configure structured logging for Application Insights."""
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_data = {
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            # Add extra fields from the record
            for key, value in record.__dict__.items():
                if key not in (
                    "name", "msg", "args", "created", "filename",
                    "funcName", "levelname", "levelno", "lineno",
                    "module", "msecs", "message", "pathname",
                    "process", "processName", "relativeCreated",
                    "thread", "threadName", "exc_info", "exc_text",
                    "stack_info",
                ):
                    log_data[key] = value
            return json.dumps(log_data)
    
    logger = logging.getLogger()
    for handler in logger.handlers:
        handler.setFormatter(JSONFormatter())
