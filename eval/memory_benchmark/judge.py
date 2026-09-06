from __future__ import annotations
import json
from typing import Any

JUDGE_PROMPT = """Classify every required fact as used, not_used, or incorrect. A fact is used only if the answer meaningfully relies on or correctly reflects it; do not reward vague statements. Return JSON only: {\"facts\":[{\"id\":...,\"result\":...}]}."""

def parse_judge_json(content: str) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Judge returned malformed JSON") from exc
    if not isinstance(value, dict) or not isinstance(value.get("facts"), list):
        raise ValueError("Judge JSON must contain facts list")
    return value
