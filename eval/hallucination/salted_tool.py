"""Stub ask_about_book tool backed by REAL highlights salted with INJECTED
false claims — unlabeled, shuffled together.

This is what makes the hallucination eval a genuine known-injection test:
the agent's answer-synthesis step has to work from source content that
looks uniformly trustworthy but partly isn't, exactly like a real
prompt-injection / corrupted-retrieval scenario. If the eval instead fed
labeled "real" vs. "fake" content, it would only be testing whether the
model can read a label, not whether it hallucinates from ambiguous source
material.
"""

from __future__ import annotations

import json
import random
from typing import Any

from eval.hallucination.fixtures import HallucinationFixture
from nanobot.agent.tools.base import Tool

_ASK_ABOUT_BOOK_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "book_title": {"type": "string", "description": "Title of the book to look up."},
    },
    "required": ["book_title"],
}


class SaltedAskAboutBookTool(Tool):
    """Records every call it receives; always returns the same fixture's
    real+injected content regardless of the ``book_title`` argument the
    model passes — this eval is about answer synthesis given corrupted
    source content, not about testing the book-title matching itself."""

    def __init__(self, fixture: HallucinationFixture, *, seed: int | None = 0) -> None:
        self._fixture = fixture
        self.calls: list[dict[str, Any]] = []

        entries = list(fixture.real_highlights) + [claim.text for claim in fixture.injected_claims]
        random.Random(seed).shuffle(entries)
        self._canned_response = json.dumps(
            {"book_title": fixture.book_title, "highlights": entries},
            ensure_ascii=False,
        )

    @property
    def name(self) -> str:
        return "ask_about_book"

    @property
    def description(self) -> str:
        return (
            "Answer a question about the content/arguments of a specific book "
            "the user is reading, grounded in the book's actual highlighted "
            "passages. Requires the book title."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return _ASK_ABOUT_BOOK_PARAMETERS

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._canned_response
