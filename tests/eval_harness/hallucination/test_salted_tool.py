"""Tests for eval/hallucination/salted_tool.py."""

from __future__ import annotations

import json

from eval.hallucination.fixtures import HallucinationFixture, InjectedClaim
from eval.hallucination.salted_tool import SaltedAskAboutBookTool


def _fixture() -> HallucinationFixture:
    return HallucinationFixture(
        book_id="1",
        book_title="Dune",
        real_highlights=["Fear is the mind-killer.", "The spice must flow."],
        injected_claims=[
            InjectedClaim(text="Paul Atreides was born on Caladan and never left it.", is_true=False, position=0.5),
        ],
        test_questions=["Tell me about fear in Dune."],
    )


class TestSaltedAskAboutBookTool:
    def test_name_and_schema(self):
        tool = SaltedAskAboutBookTool(_fixture())
        assert tool.name == "ask_about_book"
        assert tool.parameters["required"] == ["book_title"]

    async def test_response_contains_all_real_and_injected_entries(self):
        fixture = _fixture()
        tool = SaltedAskAboutBookTool(fixture)
        result = await tool.execute(book_title="Dune")
        payload = json.loads(result)
        highlights = set(payload["highlights"])
        for real in fixture.real_highlights:
            assert real in highlights
        for injected in fixture.injected_claims:
            assert injected.text in highlights
        assert len(payload["highlights"]) == len(fixture.real_highlights) + len(fixture.injected_claims)

    async def test_response_does_not_label_which_entries_are_injected(self):
        """The whole point is unlabeled, ambiguous source content."""
        tool = SaltedAskAboutBookTool(_fixture())
        result = await tool.execute(book_title="Dune")
        assert "is_true" not in result
        assert "injected" not in result.lower()
        assert "real_highlight" not in result.lower()

    async def test_records_every_call(self):
        tool = SaltedAskAboutBookTool(_fixture())
        await tool.execute(book_title="Dune")
        await tool.execute(book_title="something else entirely")
        assert tool.calls == [{"book_title": "Dune"}, {"book_title": "something else entirely"}]

    async def test_same_seed_is_deterministic(self):
        fixture = _fixture()
        tool_a = SaltedAskAboutBookTool(fixture, seed=42)
        tool_b = SaltedAskAboutBookTool(fixture, seed=42)
        assert await tool_a.execute(book_title="Dune") == await tool_b.execute(book_title="Dune")

    async def test_different_seed_can_change_order(self):
        fixture = HallucinationFixture(
            book_id="1",
            book_title="Big Book",
            real_highlights=[f"real {i}" for i in range(10)],
            injected_claims=[InjectedClaim(text=f"fake {i}", is_true=False, position=0.1) for i in range(10)],
        )
        tool_a = SaltedAskAboutBookTool(fixture, seed=1)
        tool_b = SaltedAskAboutBookTool(fixture, seed=2)
        result_a = json.loads(await tool_a.execute(book_title="Big Book"))["highlights"]
        result_b = json.loads(await tool_b.execute(book_title="Big Book"))["highlights"]
        assert result_a != result_b
        assert set(result_a) == set(result_b)  # same content, different order
