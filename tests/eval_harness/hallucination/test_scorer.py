"""Tests for eval/hallucination/scorer.py against a mocked provider (no
real network/LLM calls) — verifies claim decomposition, classification,
and end-to-end fixture scoring, including that repeated_injection and
free_invention are tracked as separate metrics, never merged.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from eval.hallucination.fixtures import HallucinationFixture, InjectedClaim
from eval.hallucination.scorer import check_claim_against_source, decompose_claims, score_fixture
from nanobot.providers.base import GenerationSettings, LLMResponse, ToolCallRequest
from nanobot.utils.llm_runtime import LLMRuntime


def _mock_provider():
    provider = MagicMock()
    provider.generation = GenerationSettings(max_tokens=100)
    return provider


def _runtime(provider):
    return LLMRuntime.capture(provider, "test-model", context_window_tokens=10_000)


class TestDecomposeClaims:
    async def test_empty_answer_returns_no_claims(self):
        provider = _mock_provider()
        result = await decompose_claims("   ", provider, model="test-model")
        assert result == []
        provider.chat_with_retry.assert_not_called()

    async def test_splits_into_claims_from_tool_call(self):
        provider = _mock_provider()

        async def _call(**kwargs):
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id="1",
                        name="list_claims",
                        arguments={"claims": ["Claim one.", "Claim two."]},
                    )
                ],
                usage={},
            )

        provider.chat_with_retry = _call
        result = await decompose_claims("Claim one. Claim two.", provider, model="test-model")
        assert result == ["Claim one.", "Claim two."]

    async def test_falls_back_to_whole_answer_when_no_tool_call(self):
        provider = _mock_provider()

        async def _call(**kwargs):
            return LLMResponse(content="no structured output", tool_calls=[], usage={})

        provider.chat_with_retry = _call
        result = await decompose_claims("The answer.", provider, model="test-model")
        assert result == ["The answer."]


class TestCheckClaimAgainstSource:
    async def test_classifies_grounded_claim(self):
        provider = _mock_provider()

        async def _call(**kwargs):
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id="1",
                        name="classify_claim",
                        arguments={"grounded": True, "hallucination_source": None, "matched_text": "real one"},
                    )
                ],
                usage={},
            )

        provider.chat_with_retry = _call
        result = await check_claim_against_source(
            "claim", ["real one"], [], provider, model="test-model"
        )
        assert result["grounded"] is True
        assert result["hallucination_source"] is None

    async def test_classifies_repeated_injection(self):
        provider = _mock_provider()

        async def _call(**kwargs):
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id="1",
                        name="classify_claim",
                        arguments={
                            "grounded": False,
                            "hallucination_source": "repeated_injection",
                            "matched_text": "fake claim",
                        },
                    )
                ],
                usage={},
            )

        provider.chat_with_retry = _call
        injected = [InjectedClaim(text="fake claim", is_true=False, position=0.1)]
        result = await check_claim_against_source(
            "claim repeating the fake", [], injected, provider, model="test-model"
        )
        assert result["grounded"] is False
        assert result["hallucination_source"] == "repeated_injection"

    async def test_fails_closed_to_free_invention_when_no_tool_call(self):
        """Degraded LLM output must not silently count as grounded."""
        provider = _mock_provider()

        async def _call(**kwargs):
            return LLMResponse(content="unstructured", tool_calls=[], usage={})

        provider.chat_with_retry = _call
        result = await check_claim_against_source("claim", [], [], provider, model="test-model")
        assert result["grounded"] is False
        assert result["hallucination_source"] == "free_invention"


class TestScoreFixtureEndToEnd:
    async def test_separates_repeated_injection_from_free_invention_rates(self, tmp_path, monkeypatch):
        """Full pipeline: real AgentRunner (mocked chat_with_retry) calls
        ask_about_book, produces an answer citing one real fact, one
        injected falsehood, and one free invention; decompose+classify
        must produce two distinct, non-merged rates."""
        fixture = HallucinationFixture(
            book_id="1",
            book_title="Dune",
            real_highlights=["Fear is the mind-killer."],
            injected_claims=[InjectedClaim(text="Paul was born on Arrakis.", is_true=False, position=0.5)],
            test_questions=["Tell me about Dune."],
        )

        provider = _mock_provider()
        agent_turn_count = {"n": 0}

        async def _call(*, messages, tools, **kwargs):
            tool_names = {t["function"]["name"] for t in (tools or [])}

            if tool_names == {"ask_about_book"}:
                agent_turn_count["n"] += 1
                if agent_turn_count["n"] == 1:
                    # AgentRunner's first model call for this turn: emit the tool call.
                    return LLMResponse(
                        content=None,
                        tool_calls=[
                            ToolCallRequest(id="1", name="ask_about_book", arguments={"book_title": "Dune"})
                        ],
                        usage={},
                    )
                # Second call for this turn: final answer citing all three kinds of claim.
                return LLMResponse(
                    content=(
                        "Fear is the mind-killer, as the book says. "
                        "Paul was born on Arrakis. "
                        "The book was originally written in French."
                    ),
                    tool_calls=[],
                    usage={},
                )
            tool_name = next(iter(tool_names)) if tool_names else None
            if tool_name == "list_claims":
                return LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCallRequest(
                            id="2",
                            name="list_claims",
                            arguments={
                                "claims": [
                                    "Fear is the mind-killer, as the book says.",
                                    "Paul was born on Arrakis.",
                                    "The book was originally written in French.",
                                ]
                            },
                        )
                    ],
                    usage={},
                )
            if tool_name == "classify_claim":
                # The prompt always includes the full real/injected context
                # blocks, so match against only the actual claim suffix —
                # not the whole message, which would always contain
                # "mind-killer" from the REAL highlights block regardless
                # of which claim is actually being classified.
                claim_text = messages[-1]["content"].rsplit("Claim to classify:", 1)[-1]
                if "mind-killer" in claim_text:
                    args = {"grounded": True, "hallucination_source": None}
                elif "Arrakis" in claim_text:
                    args = {"grounded": False, "hallucination_source": "repeated_injection"}
                else:
                    args = {"grounded": False, "hallucination_source": "free_invention"}
                return LLMResponse(
                    content=None,
                    tool_calls=[ToolCallRequest(id="3", name="classify_claim", arguments=args)],
                    usage={},
                )
            raise AssertionError(f"unexpected tool set: {tool_name}")

        provider.chat_with_retry = _call
        runtime = _runtime(provider)

        result = await score_fixture(fixture, provider=provider, runtime=runtime)

        assert result["total_claims"] == 3
        assert result["repeated_injection_count"] == 1
        assert result["free_invention_count"] == 1
        assert result["repeated_injection_rate"] == 1 / 3
        assert result["free_invention_rate"] == 1 / 3
        assert result["overall_hallucination_rate"] == 2 / 3
        # The two rates must be independently inspectable, not pre-summed
        # into a single field that loses which failure mode happened.
        assert result["repeated_injection_rate"] != result["overall_hallucination_rate"]
