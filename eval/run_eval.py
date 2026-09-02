"""Tool-calling success rate evaluation CLI.

Runs every case in eval/tool_call_cases.py through a real, configured LLM
(via the same nanobot/providers/factory.py + AgentRunner machinery the
product uses) against a self-contained stub tool registry, scores each
case, prints a results table + aggregate metrics, and writes full results
(including raw traces) to eval/results/{timestamp}.json.

Usage:
    python -m eval.run_eval
    python -m eval.run_eval --preset my-preset
    python -m eval.run_eval --max-iterations 4

Requires a working nanobot provider configuration (~/.nanobot/config.json
with at least one provider's API key set, or the relevant env var) — this
harness makes real LLM calls on purpose, to measure actual tool-selection
behavior rather than scripted responses. It does NOT require the gateway,
WebSocket channel, or any other product-layer process to be running.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.scorer import compute_metrics, score_case
from eval.stub_tools import build_stub_registry
from eval.tool_call_cases import EVAL_CASES, ToolCallCase
from eval.trace_capture import DEFAULT_MAX_ITERATIONS, run_turn_with_trace
from nanobot.config.loader import ConfigLoadError, load_config, resolve_config_env_vars
from nanobot.providers.factory import make_provider
from nanobot.session.manager import SessionManager
from nanobot.utils.llm_runtime import LLMRuntime

RESULTS_DIR = Path(__file__).parent / "results"

EVAL_SYSTEM_PROMPT = """You are a reading companion agent for the user's WeRead library.

You have tools for fetching the user's live reading data (shelf contents,
progress, notes/highlights, stats, reading profile) and for taking actions
on their behalf (adding books, generating digests, answering questions
about a specific book's content).

Every one of these tools reflects live, personal state that can change at
any time outside this conversation. Always call the relevant tool for a
fresh answer — never answer a shelf/progress/notes/stats/profile question
from something you or the user said earlier in this conversation, even if
it looks like the same question was already answered. If the user asks you
to add or save something, actually call the tool for it rather than just
acknowledging the request in text.

For questions that don't need any of the user's personal reading data —
general knowledge, opinions, or questions about you — just answer directly
without calling a tool.
"""


def _case_session_key(case: ToolCallCase) -> str:
    return f"eval:group:{case.session_group}" if case.session_group else f"eval:case:{case.id}"


def _repeat_turn_case_ids(cases: list[ToolCallCase]) -> set[str]:
    """Case ids that are NOT the first turn in their session_group — i.e.
    cases that actually had prior-turn history available to (mis)answer
    from. Used only to make the table's "(from history)" annotation
    accurate; it must never apply to a case running in a fresh, isolated
    session, where there is no history to have come from."""
    seen_groups: set[str] = set()
    repeat_ids: set[str] = set()
    for case in cases:
        if case.session_group is None:
            continue
        if case.session_group in seen_groups:
            repeat_ids.add(case.id)
        else:
            seen_groups.add(case.session_group)
    return repeat_ids


def _format_actual(
    actual_tool: str | None,
    invocation_correct: bool,
    expected_tool: str | None,
    is_repeat_turn: bool,
) -> str:
    if actual_tool is not None:
        return actual_tool
    missed_positive = not invocation_correct and expected_tool is not None
    if missed_positive and is_repeat_turn:
        return "None (from history)"
    return "None"


def _expected_display(c: dict[str, Any]) -> str:
    sequence = c.get("expected_tool_sequence")
    return " → ".join(sequence) if sequence else str(c["expected_tool"])


def _print_table(scored_cases: list[dict[str, Any]], repeat_turn_ids: set[str]) -> None:
    def actual_display(c: dict[str, Any]) -> str:
        return _format_actual(
            c["actual_tool"], c["invocation_correct"], c["expected_tool"], c["case_id"] in repeat_turn_ids
        )

    id_w = max(len("CASE"), *(len(c["case_id"]) for c in scored_cases))
    exp_w = max(len("EXPECTED"), *(len(_expected_display(c)) for c in scored_cases))
    act_w = max(len("ACTUAL"), *(len(actual_display(c)) for c in scored_cases))

    header = f"{'CASE':<{id_w}}  {'EXPECTED':<{exp_w}}  {'ACTUAL':<{act_w}}  PASS"
    print(header)
    print("-" * len(header))
    for c in scored_cases:
        mark = "✓" if c["invocation_correct"] else "✗"
        print(
            f"{c['case_id']:<{id_w}}  {_expected_display(c):<{exp_w}}  "
            f"{actual_display(c):<{act_w}}  {mark}"
        )
    print()


def _print_metrics(metrics: dict[str, Any]) -> None:
    def fmt(value: float | None) -> str:
        return f"{value:.2f}" if value is not None else "N/A"

    print(f"Invocation Recall: {fmt(metrics['invocation_recall'])}")
    print(f"Invocation Precision: {fmt(metrics['invocation_precision'])}")
    print(f"Negative Case Accuracy: {fmt(metrics['negative_case_accuracy'])}")
    print(f"Argument Accuracy: {fmt(metrics['argument_accuracy'])}")
    print(f"Sequence Accuracy: {fmt(metrics['sequence_accuracy'])}")
    print(f"Total Cases: {metrics['total_cases']}")


async def _run_all(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        config = resolve_config_env_vars(load_config())
    except ConfigLoadError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        preset = config.resolve_preset(args.preset)
        provider = make_provider(config, preset_name=args.preset)
    except (ValueError, KeyError) as exc:
        print(
            f"Could not build an LLM provider from your nanobot config: {exc}\n"
            "Configure at least one provider (see `nanobot onboard` or "
            "~/.nanobot/config.json) before running the eval.",
            file=sys.stderr,
        )
        sys.exit(1)

    runtime = LLMRuntime.capture(
        provider,
        preset.model,
        context_window_tokens=preset.context_window_tokens,
        model_preset=args.preset,
    )
    registry = build_stub_registry()

    scratch_workspace = Path(tempfile.mkdtemp(prefix="nanobot-eval-workspace-"))
    sessions = SessionManager(scratch_workspace)

    scored_cases: list[dict[str, Any]] = []
    for case in EVAL_CASES:
        trace = await run_turn_with_trace(
            provider=provider,
            runtime=runtime,
            registry=registry,
            system_prompt=EVAL_SYSTEM_PROMPT,
            sessions=sessions,
            session_key=_case_session_key(case),
            question=case.question,
            max_iterations=args.max_iterations,
        )
        scored = score_case(case, trace)
        scored["trace"] = {
            "tool_calls": trace.tool_calls,
            "final_answer": trace.final_answer,
            "stop_reason": trace.stop_reason,
            "error": trace.error,
        }
        scored_cases.append(scored)

    metrics = compute_metrics(scored_cases)
    return scored_cases, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset", default=None, help="Named model preset to use (default: the configured default preset)."
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help=f"Max tool-calling iterations per turn (default: {DEFAULT_MAX_ITERATIONS}).",
    )
    args = parser.parse_args()

    scored_cases, metrics = asyncio.run(_run_all(args))

    _print_table(scored_cases, _repeat_turn_case_ids(EVAL_CASES))
    _print_metrics(metrics)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out_path.write_text(
        json.dumps({"cases": scored_cases, "metrics": metrics}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
