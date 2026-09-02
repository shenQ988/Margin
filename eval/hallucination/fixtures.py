"""Data model + JSON (de)serialization for hallucination-eval fixtures.

A fixture pairs REAL highlight text pulled from the user's own WeRead
shelf (see build_fixtures.py) with a small number of deliberately false
"injected" claims styled to blend in with the real highlights. Nothing in
this module fabricates book data — it's pure data model + I/O; real
WeRead data is only ever fetched in build_fixtures.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast


@dataclass
class InjectedClaim:
    text: str  # the claim itself
    is_true: bool  # ground truth label — always False for a planted injection
    position: float  # 0..1 proxy for reading-progress location, derived
    # from where in the real highlight order this claim was placed, so it
    # reads as plausible in context rather than appearing out of nowhere
    why_false: str = ""  # human/LLM-readable note on why this is false —
    # not scored, purely to speed up manual review of fixtures_draft.json

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "is_true": self.is_true,
            "position": self.position,
            "why_false": self.why_false,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InjectedClaim:
        return cls(
            text=str(data["text"]),
            is_true=bool(data["is_true"]),
            position=float(data["position"]),
            why_false=str(data.get("why_false", "")),
        )


@dataclass
class HallucinationFixture:
    book_id: str
    book_title: str
    real_highlights: list[str]  # actual highlights pulled from WeRead for
    # this book, unmodified
    injected_claims: list[InjectedClaim] = field(default_factory=list)
    test_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "book_title": self.book_title,
            "real_highlights": list(self.real_highlights),
            "injected_claims": [c.to_dict() for c in self.injected_claims],
            "test_questions": list(self.test_questions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HallucinationFixture:
        return cls(
            book_id=str(data["book_id"]),
            book_title=str(data["book_title"]),
            real_highlights=[str(h) for h in data.get("real_highlights", [])],
            injected_claims=[InjectedClaim.from_dict(c) for c in data.get("injected_claims", [])],
            test_questions=[str(q) for q in data.get("test_questions", [])],
        )


def save_fixtures(fixtures: list[HallucinationFixture], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([f.to_dict() for f in fixtures], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_fixtures(path: Path) -> list[HallucinationFixture]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a JSON array of fixtures, got {type(raw).__name__}")
    entries = cast("list[dict[str, Any]]", raw)
    return [HallucinationFixture.from_dict(entry) for entry in entries]
