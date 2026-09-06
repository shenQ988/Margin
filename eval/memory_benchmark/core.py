from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class MemoryCase:
    id: str
    sessions: list[list[dict[str, str]]]
    query: str
    required_facts: list[dict[str, str]]


def load_cases(path: Path) -> list[MemoryCase]:
    cases = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            cases.append(MemoryCase(raw["id"], [s["messages"] for s in raw["sessions"]], raw["evaluation"]["query"], raw["evaluation"]["required_facts"]))
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid memory case at {path}:{line_no}") from exc
    return cases


def score_facts(required_facts: list[dict[str, str]], judge: dict[str, Any]) -> dict[str, str]:
    allowed = {fact["id"] for fact in required_facts}
    results = {fact_id: "not_used" for fact_id in allowed}
    for item in judge.get("facts", []):
        if isinstance(item, dict) and item.get("id") in allowed and item.get("result") in {"used", "not_used", "incorrect"}:
            results[item["id"]] = item["result"]
    return results


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    facts = [result for row in rows for result in row["required_fact_results"].values()]
    return {"cases": len(rows), "required_facts": len(facts), "recall": sum(x == "used" for x in facts) / len(facts) if facts else 0.0,
            "incorrect": sum(x == "incorrect" for x in facts), "avg_answer_input_tokens": mean([r["answer_input_tokens"] for r in rows]) if rows else 0.0,
            "avg_maintenance_input_tokens": mean([r["maintenance_input_tokens"] for r in rows]) if rows else 0.0}
