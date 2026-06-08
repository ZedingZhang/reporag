from __future__ import annotations

import json
import logging
import time

from langgraph.graph import END, StateGraph

from app.agent.prompts import (
    PLANNER_PROMPT,
    SUMMARIZER_PROMPT,
    TASK_CLASSIFIER_PROMPT,
)
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


class _AgentNodeContext:
    def __init__(self, chat_provider, retriever, session_factory):
        self.chat = chat_provider
        self.retriever = retriever
        self.session_factory = session_factory

    def _record_step(self, state: AgentState, node_name: str, tool_name=None,
                     input_data=None, output_data=None, status="completed",
                     latency_ms=None) -> None:
        from app.db.models import AgentStep
        session = self.session_factory()
        try:
            step = AgentStep(
                run_id=state.run_id,
                step_index=len(state.plan) + 1,
                node_name=node_name,
                tool_name=tool_name,
                input_json=input_data,
                output_json=output_data,
                status=status,
                latency_ms=latency_ms,
            )
            session.add(step)
            session.commit()
        except Exception:
            logger.exception("Failed to record step: %s", node_name)
        finally:
            session.close()

    def classify_task(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        prompt = TASK_CLASSIFIER_PROMPT.format(task=state.task)
        try:
            result = self.chat.chat([
                {"role": "system", "content": "Classify repository maintenance tasks."},
                {"role": "user", "content": prompt},
            ])
            state.task_type = result.strip().lower()
        except Exception:
            logger.warning("Task classification failed, defaulting to question")
            state.task_type = "question"
        self._record_step(
            state, "classify_task",
            output_data={"task_type": state.task_type},
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def retrieve_context(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        state.context_queries = [state.task]
        all_chunks = self.retriever.retrieve(
            query=state.task, repo_id=state.repo_id, top_k=state.top_k * 2,
        )
        state.retrieved_context = []
        seen_paths: set[str] = set()
        for c in all_chunks:
            if c.path and c.path not in seen_paths:
                seen_paths.add(c.path)
                state.target_files.append(c.path)
            state.retrieved_context.append({
                "chunk_id": c.chunk_id,
                "path": c.path,
                "chunk_type": c.chunk_type,
                "content": c.content[:1000],
                "github_url": c.github_url,
                "line_start": c.line_start,
                "line_end": c.line_end,
                "score": round(c.score, 4),
            })
        self._record_step(
            state, "retrieve_context",
            output_data={
                "num_chunks": len(state.retrieved_context),
                "target_files": state.target_files[:10],
            },
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def build_plan(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        evidence = _format_evidence(state.retrieved_context)
        prompt = PLANNER_PROMPT.format(task=state.task, evidence=evidence)
        try:
            result = self.chat.chat([
                {"role": "system", "content": "You plan code maintenance tasks."},
                {"role": "user", "content": prompt},
            ])
            plan = _parse_json(result)
            if not plan:
                state.plan = [{
                    "goal": "Analyze task from retrieved context",
                    "files": state.target_files[:5],
                    "evidence_urls": [],
                    "risk_level": "low",
                    "requires_approval": False,
                }]
            else:
                state.task_type = plan.get("task_type", state.task_type)
                state.plan = plan.get("steps", [plan])
        except Exception:
            logger.exception("Plan generation failed")
            state.plan = [{
                "goal": "Error generating plan",
                "files": [],
                "evidence_urls": [],
                "risk_level": "low",
                "requires_approval": False,
            }]
            state.errors.append("Plan generation failed")
        self._record_step(
            state, "build_plan",
            output_data={"num_steps": len(state.plan)},
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state

    def summarize(self, state: AgentState) -> AgentState:
        t0 = time.monotonic()
        prompt = SUMMARIZER_PROMPT.format(
            task=state.task, mode=state.mode, task_type=state.task_type,
            plan=json.dumps(state.plan, indent=2),
            status=state.status,
            errors=json.dumps(state.errors) if state.errors else "none",
        )
        try:
            state.final_summary = self.chat.chat([
                {"role": "system", "content": "You summarize agent runs for developers."},
                {"role": "user", "content": prompt},
            ])
        except Exception:
            logger.exception("Summary generation failed")
            state.final_summary = "Summary generation failed."
            state.errors.append("Summary generation failed")
        state.status = "completed"
        self._record_step(
            state, "summarize",
            output_data={"summary": state.final_summary[:500]},
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return state


def _format_evidence(context: list[dict]) -> str:
    parts: list[str] = []
    for i, item in enumerate(context):
        location = ""
        if item.get("path"):
            location = f" [{item['path']}"
            if item.get("line_start"):
                location += f":L{item['line_start']}"
            location += "]"
        url = item.get("github_url", "")
        parts.append(
            f"[Source {i + 1}]{location}\nURL: {url}\n{item.get('content', '')[:1500]}"
        )
    return "\n\n---\n\n".join(parts)


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def build_agent_graph(chat_provider, retriever, session_factory):
    ctx = _AgentNodeContext(chat_provider, retriever, session_factory)

    workflow = StateGraph(AgentState)

    workflow.add_node("classify_task", ctx.classify_task)
    workflow.add_node("retrieve_context", ctx.retrieve_context)
    workflow.add_node("build_plan", ctx.build_plan)
    workflow.add_node("summarize", ctx.summarize)

    workflow.set_entry_point("classify_task")
    workflow.add_edge("classify_task", "retrieve_context")
    workflow.add_edge("retrieve_context", "build_plan")
    workflow.add_edge("build_plan", "summarize")
    workflow.add_edge("summarize", END)

    return workflow.compile()
