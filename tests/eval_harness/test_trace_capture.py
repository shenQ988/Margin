"""Integration tests for eval/trace_capture.py against a mocked provider.

These exercise the real, unmodified AgentRunner — only the LLM call itself
is mocked (no network), so this verifies trace extraction and session
history sharing work correctly against actual runner behavior, without
requiring real API credentials to run in CI.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from eval.stub_tools import build_stub_registry
from eval.trace_capture import run_turn_with_trace
from nanobot.providers.base import GenerationSettings, LLMResponse, ToolCallRequest
from nanobot.session.manager import SessionManager
from nanobot.utils.llm_runtime import LLMRuntime

SYSTEM_PROMPT = "test system prompt"


def _mock_provider(responses: list[LLMResponse]):
    provider = MagicMock()
    provider.generation = GenerationSettings(max_tokens=100)
    calls = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[i]

    provider.chat_with_retry = chat_with_retry
    return provider, calls


def _runtime(provider):
    return LLMRuntime.capture(provider, "test-model", context_window_tokens=10_000)


class TestRunTurnWithTrace:
    async def test_captures_a_single_tool_call_in_order(self, tmp_path):
        responses = [
            LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(id="1", name="weread_shelf", arguments={})],
                usage={},
            ),
            LLMResponse(content="Here's your shelf.", tool_calls=[], usage={}),
        ]
        provider, _ = _mock_provider(responses)
        sessions = SessionManager(tmp_path)

        trace = await run_turn_with_trace(
            provider=provider,
            runtime=_runtime(provider),
            registry=build_stub_registry(),
            system_prompt=SYSTEM_PROMPT,
            sessions=sessions,
            session_key="eval:case:t1",
            question="what's on my bookshelf?",
        )

        assert trace.tool_calls == [{"name": "weread_shelf", "args": {}}]
        assert trace.final_answer == "Here's your shelf."

    async def test_no_tool_call_gives_empty_trace(self, tmp_path):
        responses = [LLMResponse(content="Jane Austen wrote it.", tool_calls=[], usage={})]
        provider, _ = _mock_provider(responses)
        sessions = SessionManager(tmp_path)

        trace = await run_turn_with_trace(
            provider=provider,
            runtime=_runtime(provider),
            registry=build_stub_registry(),
            system_prompt=SYSTEM_PROMPT,
            sessions=sessions,
            session_key="eval:case:t2",
            question="who wrote Pride and Prejudice?",
        )

        assert trace.tool_calls == []
        assert trace.final_answer == "Jane Austen wrote it."

    async def test_captures_tool_call_arguments(self, tmp_path):
        responses = [
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id="1", name="weread_progress", arguments={"book_title": "Sapiens"}
                    )
                ],
                usage={},
            ),
            LLMResponse(content="42%.", tool_calls=[], usage={}),
        ]
        provider, _ = _mock_provider(responses)
        sessions = SessionManager(tmp_path)

        trace = await run_turn_with_trace(
            provider=provider,
            runtime=_runtime(provider),
            registry=build_stub_registry(),
            system_prompt=SYSTEM_PROMPT,
            sessions=sessions,
            session_key="eval:case:t3",
            question="how far into Sapiens am I?",
        )

        assert trace.tool_calls == [{"name": "weread_progress", "args": {"book_title": "Sapiens"}}]

    async def test_shared_session_key_carries_history_to_second_call(self, tmp_path):
        """Regression-case plumbing: two calls with the same session_key must
        let the second call's prompt include the first call's turn."""
        first_responses = [
            LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(id="1", name="weread_shelf", arguments={})],
                usage={},
            ),
            LLMResponse(content="You have 3 books.", tool_calls=[], usage={}),
        ]
        second_responses = [
            LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(id="2", name="weread_shelf", arguments={})],
                usage={},
            ),
            LLMResponse(content="Still 3 books.", tool_calls=[], usage={}),
        ]
        provider, _ = _mock_provider(first_responses)
        sessions = SessionManager(tmp_path)
        registry = build_stub_registry()
        runtime = _runtime(provider)

        await run_turn_with_trace(
            provider=provider,
            runtime=runtime,
            registry=registry,
            system_prompt=SYSTEM_PROMPT,
            sessions=sessions,
            session_key="eval:group:repeat_shelf",
            question="what's on my bookshelf?",
        )

        provider2, calls2 = _mock_provider(second_responses)
        seen_prompts: list[list[dict]] = []

        async def chat_with_retry_capturing(*, messages, **kwargs):
            seen_prompts.append(messages)
            i = min(calls2["n"], len(second_responses) - 1)
            calls2["n"] += 1
            return second_responses[i]

        provider2.chat_with_retry = chat_with_retry_capturing

        second_trace = await run_turn_with_trace(
            provider=provider2,
            runtime=_runtime(provider2),
            registry=registry,
            system_prompt=SYSTEM_PROMPT,
            sessions=sessions,
            session_key="eval:group:repeat_shelf",
            question="what's on my bookshelf again?",
        )

        assert second_trace.tool_calls == [{"name": "weread_shelf", "args": {}}]
        # The first turn's question and answer must be visible as history
        # in the second call's prompt.
        first_call_messages = seen_prompts[0]
        joined = " ".join(str(m.get("content")) for m in first_call_messages)
        assert "what's on my bookshelf?" in joined
        assert "You have 3 books." in joined

    async def test_fresh_session_keys_do_not_share_history(self, tmp_path):
        responses = [LLMResponse(content="answer one", tool_calls=[], usage={})]
        provider, _ = _mock_provider(responses)
        sessions = SessionManager(tmp_path)
        registry = build_stub_registry()
        runtime = _runtime(provider)

        await run_turn_with_trace(
            provider=provider,
            runtime=runtime,
            registry=registry,
            system_prompt=SYSTEM_PROMPT,
            sessions=sessions,
            session_key="eval:case:isolated_a",
            question="question A",
        )

        provider2, calls2 = _mock_provider([LLMResponse(content="answer two", tool_calls=[], usage={})])
        seen_prompts: list[list[dict]] = []

        async def chat_with_retry_capturing(*, messages, **kwargs):
            seen_prompts.append(messages)
            return LLMResponse(content="answer two", tool_calls=[], usage={})

        provider2.chat_with_retry = chat_with_retry_capturing

        await run_turn_with_trace(
            provider=provider2,
            runtime=_runtime(provider2),
            registry=registry,
            system_prompt=SYSTEM_PROMPT,
            sessions=sessions,
            session_key="eval:case:isolated_b",
            question="question B",
        )

        joined = " ".join(str(m.get("content")) for m in seen_prompts[0])
        assert "question A" not in joined
        assert "answer one" not in joined
