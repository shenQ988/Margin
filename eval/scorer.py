"""Score individual eval cases and compute aggregate tool-calling metrics."""

from __future__ import annotations

from typing import Any

from eval.tool_call_cases import ToolCallCase
from eval.trace_capture import TurnTrace


def _score_sequence(case: ToolCallCase, trace: TurnTrace) -> bool | None:
    """Soft signal for multi-step cases: did the actual tool-call sequence
    match ``expected_tool_sequence`` exactly (as a prefix — extra calls
    after the expected steps don't fail this)? None when the case doesn't
    specify a sequence at all. A short sequence that still answers the
    question (e.g. stopping after step 1) is judged separately by whoever
    reads ``sequence_accuracy`` — it does NOT fail invocation_correct,
    which only ever looks at the first call."""
    if not case.expected_tool_sequence:
        return None
    actual_names = [call["name"] for call in trace.tool_calls[: len(case.expected_tool_sequence)]]
    return actual_names == case.expected_tool_sequence


def score_case(case: ToolCallCase, trace: TurnTrace) -> dict[str, Any]:
    """Score one case against its trace. Only the FIRST tool call is judged
    against ``expected_tool``/``expected_args`` for the hard pass/fail
    signal — a case's label describes what should happen first, not
    everything the agent might do after. ``expected_tool_sequence``, when
    set, adds a softer ``sequence_correct`` signal on top (see
    ``_score_sequence``) rather than replacing the first-call check."""
    actual_tool = trace.tool_calls[0]["name"] if trace.tool_calls else None

    invocation_correct = actual_tool == case.expected_tool

    args_correct = None
    if case.expected_tool and invocation_correct and case.expected_args:
        actual_args: dict[str, Any] = trace.tool_calls[0]["args"]
        expected_args: dict[str, Any] = case.expected_args
        args_correct = all(actual_args.get(k) == v for k, v in expected_args.items())

    return {
        "case_id": case.id,
        "category": case.category,
        "question": case.question,
        "expected_tool": case.expected_tool,
        "expected_tool_sequence": case.expected_tool_sequence,
        "actual_tool": actual_tool,
        "actual_tool_sequence": [call["name"] for call in trace.tool_calls],
        "invocation_correct": invocation_correct,
        "args_correct": args_correct,
        "sequence_correct": _score_sequence(case, trace),
        "extra_tool_calls": len(trace.tool_calls) > (1 if case.expected_tool else 0),
        "final_answer": trace.final_answer,
        "stop_reason": trace.stop_reason,
        "error": trace.error,
    }


def compute_metrics(scored_cases: list[dict[str, Any]]) -> dict[str, Any]:
    positive_cases = [c for c in scored_cases if c["expected_tool"] is not None]
    negative_cases = [c for c in scored_cases if c["expected_tool"] is None]

    recall = (
        sum(c["invocation_correct"] for c in positive_cases) / len(positive_cases)
        if positive_cases
        else None
    )
    # precision: of all cases where SOME tool was called, how many were correct
    called_cases = [c for c in scored_cases if c["actual_tool"] is not None]
    precision = (
        sum(c["invocation_correct"] for c in called_cases) / len(called_cases)
        if called_cases
        else None
    )
    negative_correct_rate = (
        sum(c["invocation_correct"] for c in negative_cases) / len(negative_cases)
        if negative_cases
        else None
    )
    arg_cases = [c for c in scored_cases if c["args_correct"] is not None]
    arg_accuracy = (
        sum(c["args_correct"] for c in arg_cases) / len(arg_cases) if arg_cases else None
    )
    sequence_cases = [c for c in scored_cases if c["sequence_correct"] is not None]
    sequence_accuracy = (
        sum(c["sequence_correct"] for c in sequence_cases) / len(sequence_cases)
        if sequence_cases
        else None
    )

    return {
        "invocation_recall": recall,  # did it call the right tool when it should have
        "invocation_precision": precision,  # of tools it DID call, how many were right
        "negative_case_accuracy": negative_correct_rate,  # did it correctly call NOTHING when nothing was needed
        "argument_accuracy": arg_accuracy,
        "sequence_accuracy": sequence_accuracy,  # for expected_tool_sequence cases only
        "total_cases": len(scored_cases),
    }
