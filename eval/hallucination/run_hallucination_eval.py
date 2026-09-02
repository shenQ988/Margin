"""Stage 2 of the hallucination eval: score human-reviewed fixtures.

Usage:
    python -m eval.hallucination.run_hallucination_eval
    python -m eval.hallucination.run_hallucination_eval --preset my-preset

Reads ONLY eval/hallucination/fixtures_reviewed.json — NEVER
fixtures_draft.json directly, since draft fixtures haven't been manually
verified yet (see build_fixtures.py). If fixtures_reviewed.json doesn't
exist, this exits with instructions instead of silently falling back to
the draft.

Requires a working nanobot provider configuration (same as
eval/run_eval.py) — this makes real LLM calls, both to run the agent turn
under test and to decompose/classify its answer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.hallucination.fixtures import load_fixtures
from eval.hallucination.llm_config import build_provider_and_runtime
from eval.hallucination.scorer import score_fixture

REVIEWED_PATH = Path(__file__).parent / "fixtures_reviewed.json"
DRAFT_PATH = Path(__file__).parent / "fixtures_draft.json"
RESULTS_DIR = Path(__file__).parent / "results"


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "N/A"


def _claim_label(claim: dict[str, Any]) -> str:
    if claim["grounded"]:
        return "REAL HIGHLIGHT - grounded"
    if claim["hallucination_source"] == "repeated_injection":
        return "REPEATED INJECTION - hallucinated"
    return "FREE INVENTION - hallucinated"


def _print_fixture_report(result: dict[str, Any]) -> None:
    print(f"=== Book: {result['book_title']} ===")
    for q in result["questions"]:
        print(f'Question: "{q["question"]}"')
        for claim in q["claims"]:
            print(f'Claim: "{claim["claim"]}" [{_claim_label(claim)}]')
        print()

    print(f"Repeated-injection rate: {_fmt(result['repeated_injection_rate'])}")
    print(f"Free-invention rate: {_fmt(result['free_invention_rate'])}")
    print(f"Overall hallucination rate: {_fmt(result['overall_hallucination_rate'])}")
    print()


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(r["total_claims"] for r in results)
    repeated = sum(r["repeated_injection_count"] for r in results)
    invented = sum(r["free_invention_count"] for r in results)
    return {
        "total_claims": total,
        "repeated_injection_count": repeated,
        "free_invention_count": invented,
        "repeated_injection_rate": (repeated / total) if total else None,
        "free_invention_rate": (invented / total) if total else None,
        "overall_hallucination_rate": ((repeated + invented) / total) if total else None,
    }


async def _run_all(preset: str | None) -> list[dict[str, Any]]:
    if not REVIEWED_PATH.exists():
        print(
            f"{REVIEWED_PATH} does not exist yet.\n\n"
            "Run the build stage first:\n"
            "  python -m eval.hallucination.build_fixtures --list\n"
            "  python -m eval.hallucination.build_fixtures --book-ids <id1> <id2> ...\n\n"
            f"Then manually review {DRAFT_PATH} and copy/edit it into {REVIEWED_PATH} "
            "yourself — this step is never automated.",
            file=sys.stderr,
        )
        sys.exit(1)

    fixtures = load_fixtures(REVIEWED_PATH)
    if not fixtures:
        print(f"{REVIEWED_PATH} contains no fixtures.", file=sys.stderr)
        sys.exit(1)

    provider, runtime = build_provider_and_runtime(preset)

    results: list[dict[str, Any]] = []
    for fixture in fixtures:
        results.append(await score_fixture(fixture, provider=provider, runtime=runtime))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", default=None, help="Named model preset to use.")
    args = parser.parse_args()

    results = asyncio.run(_run_all(args.preset))

    for result in results:
        _print_fixture_report(result)

    aggregate = _aggregate(results)
    print("=== AGGREGATE (across all books) ===")
    print(f"Repeated-injection rate: {_fmt(aggregate['repeated_injection_rate'])}")
    print(f"Free-invention rate: {_fmt(aggregate['free_invention_rate'])}")
    print(f"Overall hallucination rate: {_fmt(aggregate['overall_hallucination_rate'])}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out_path.write_text(
        json.dumps({"fixtures": results, "aggregate": aggregate}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
