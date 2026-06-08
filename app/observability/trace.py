from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TraceSpan:
    span_id: str
    parent_id: str | None = None
    name: str = ""
    status: str = "started"
    start_ms: int = 0
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class TraceCollector:
    def __init__(self) -> None:
        self._spans: dict[str, TraceSpan] = {}
        self._metrics: dict[str, list[float]] = {}

    def start_span(self, span_id: str, name: str, parent_id: str | None = None) -> TraceSpan:
        span = TraceSpan(
            span_id=span_id, parent_id=parent_id, name=name,
            start_ms=int(time.monotonic() * 1000),
        )
        self._spans[span_id] = span
        return span

    def end_span(self, span_id: str, status: str = "completed",
                 metadata: dict[str, Any] | None = None) -> TraceSpan | None:
        span = self._spans.get(span_id)
        if not span:
            return None
        span.duration_ms = int(time.monotonic() * 1000) - span.start_ms
        span.status = status
        if metadata:
            span.metadata.update(metadata)
        return span

    def record_metric(self, name: str, value: float) -> None:
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(value)

    def get_metrics(self) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for name, values in self._metrics.items():
            if values:
                result[name] = {
                    "count": len(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }
        return result

    def get_spans(self) -> list[dict[str, Any]]:
        return [
            {
                "span_id": s.span_id,
                "parent_id": s.parent_id,
                "name": s.name,
                "status": s.status,
                "duration_ms": s.duration_ms,
                "metadata": s.metadata,
            }
            for s in self._spans.values()
        ]


def record_agent_step(
    run_id: str, step_index: int, node_name: str,
    tool_name: str | None = None,
    input_data: dict | None = None,
    output_data: dict | None = None,
    status: str = "completed",
    latency_ms: int | None = None,
) -> None:
    from app.db.models import AgentStep
    from app.db.session import get_sync_session
    session = get_sync_session()
    try:
        step = AgentStep(
            run_id=run_id, step_index=step_index,
            node_name=node_name, tool_name=tool_name,
            input_json=input_data, output_json=output_data,
            status=status, latency_ms=latency_ms,
        )
        session.add(step)
        session.commit()
    except Exception:
        logger.exception("Failed to record agent step")
    finally:
        session.close()


def record_tool_execution(
    run_id: str, tool_name: str,
    input_data: dict | None = None,
    output_data: dict | None = None,
    status: str = "completed",
    latency_ms: int = 0,
) -> None:
    from app.db.models import ToolExecution
    from app.db.session import get_sync_session
    session = get_sync_session()
    try:
        te = ToolExecution(
            run_id=run_id, tool_name=tool_name,
            input_json=input_data, output_json=output_data,
            status=status, latency_ms=latency_ms,
        )
        session.add(te)
        session.commit()
    except Exception:
        logger.exception("Failed to record tool execution")
    finally:
        session.close()


def record_llm_call(
    provider: str, model: str, prompt_tokens: int = 0,
    completion_tokens: int = 0, latency_ms: int = 0,
    status: str = "completed",
) -> None:
    logger.debug(
        "LLM call: provider=%s model=%s prompt=%d completion=%d latency=%dms status=%s",
        provider, model, prompt_tokens, completion_tokens, latency_ms, status,
    )


def record_metric(name: str, value: float) -> None:
    logger.debug("Metric: %s = %s", name, value)
