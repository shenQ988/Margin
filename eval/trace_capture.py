"""Run a single agent turn and capture a structured trace of its tool calls.

Non-invasive by construction: this calls the real, unmodified
``AgentRunner.run()`` (`nanobot/agent/runner.py`) and inspects the
``AgentRunResult.messages`` it returns — no monkeypatching, no changes to
``agent/runner.py``'s tool-calling logic. Tool calls are recovered from the
assistant messages appended *during this run* (identified by slicing past
the length of the messages handed in as ``initial_messages``), so a
session's prior-turn tool calls already sitting in history are never
mistaken for new ones.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from nanobot.agent.runner import AgentRunner, AgentRunSpec
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import SessionManager
from nanobot.utils.llm_runtime import LLMRuntime

DEFAULT_MAX_ITERATIONS = 6
DEFAULT_MAX_TOOL_RESULT_CHARS = 8_000


@dataclass
class TurnTrace:
    question: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # [{"name": str, "args": dict}, ...]
    final_answer: str = ""
    stop_reason: str = "completed"
    error: str | None = None


def _extract_tool_calls(
    messages: list[dict[str, Any]],
    *,
    baseline_len: int,
) -> list[dict[str, Any]]:
    """Recover ordered tool calls made *during this turn* only."""
    calls: list[dict[str, Any]] = []
    for message in messages[baseline_len:]:
        if message.get("role") != "assistant":
            continue
        raw_tool_calls: Any = message.get("tool_calls") or []
        for tool_call in cast("list[dict[str, Any]]", raw_tool_calls):
            function = cast("dict[str, Any]", tool_call.get("function") or {})
            raw_args = function.get("arguments")
            args: dict[str, Any]
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except (TypeError, ValueError):
                args = {}
            calls.append({"name": function.get("name"), "args": args})
    return calls


async def run_turn_with_trace(
    *,
    provider: LLMProvider,
    runtime: LLMRuntime,
    registry: ToolRegistry,
    system_prompt: str,
    sessions: SessionManager,
    session_key: str,
    question: str,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    max_tool_result_chars: int = DEFAULT_MAX_TOOL_RESULT_CHARS,
) -> TurnTrace:
    """Run one turn against a real AgentRunner and return a structured trace.

    ``sessions``/``session_key`` control history sharing: pass the same
    ``session_key`` across multiple calls (see ``ToolCallCase.session_group``
    in eval/tool_call_cases.py) to let later turns see earlier ones — this
    is what regression cases need. Each call persists its own new messages
    back into the session before returning, so the next call in the same
    group sees this turn's question, tool calls, and answer as history.
    """
    session = sessions.get_or_create(session_key)
    history = session.get_history()
    initial_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": question},
    ]
    baseline_len = len(initial_messages)

    spec = AgentRunSpec(
        initial_messages=initial_messages,
        tools=registry,
        runtime=runtime,
        max_iterations=max_iterations,
        max_tool_result_chars=max_tool_result_chars,
    )
    result = await AgentRunner().run(spec)

    tool_calls = _extract_tool_calls(result.messages, baseline_len=baseline_len)

    # Persist this turn (question + everything the run appended) so a
    # later call sharing this session_key sees it as history.
    session.messages.append(
        {"role": "user", "content": question, "timestamp": datetime.now().isoformat()}
    )
    session.messages.extend(result.messages[baseline_len:])
    session.updated_at = datetime.now()
    sessions.save(session)

    return TurnTrace(
        question=question,
        tool_calls=tool_calls,
        final_answer=result.final_content or "",
        stop_reason=result.stop_reason,
        error=result.error,
    )
