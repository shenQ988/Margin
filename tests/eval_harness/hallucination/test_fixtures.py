"""Tests for eval/hallucination/fixtures.py — pure data model + JSON I/O."""

from __future__ import annotations

from eval.hallucination.fixtures import (
    HallucinationFixture,
    InjectedClaim,
    load_fixtures,
    save_fixtures,
)


def _sample_fixture() -> HallucinationFixture:
    return HallucinationFixture(
        book_id="12345",
        book_title="Sapiens",
        real_highlights=["Fiction has enabled us to cooperate flexibly in large numbers."],
        injected_claims=[
            InjectedClaim(
                text="Harari claims humans first cooperated via written contracts.",
                is_true=False,
                position=0.5,
                why_false="Contradicts the book's actual thesis about shared myths, not contracts.",
            )
        ],
        test_questions=["What does the book say enabled large-scale human cooperation?"],
    )


class TestInjectedClaimRoundTrip:
    def test_to_dict_from_dict_round_trip(self):
        claim = InjectedClaim(text="x", is_true=False, position=0.3, why_false="because")
        restored = InjectedClaim.from_dict(claim.to_dict())
        assert restored == claim

    def test_from_dict_defaults_why_false_when_missing(self):
        restored = InjectedClaim.from_dict({"text": "x", "is_true": False, "position": 0.1})
        assert restored.why_false == ""


class TestHallucinationFixtureRoundTrip:
    def test_to_dict_from_dict_round_trip(self):
        fixture = _sample_fixture()
        restored = HallucinationFixture.from_dict(fixture.to_dict())
        assert restored == fixture

    def test_from_dict_defaults_empty_lists_when_missing(self):
        restored = HallucinationFixture.from_dict({"book_id": "1", "book_title": "T"})
        assert restored.real_highlights == []
        assert restored.injected_claims == []
        assert restored.test_questions == []


class TestSaveLoadFixtures:
    def test_save_then_load_round_trips(self, tmp_path):
        fixtures = [_sample_fixture(), _sample_fixture()]
        path = tmp_path / "sub" / "fixtures.json"
        save_fixtures(fixtures, path)
        assert path.exists()

        loaded = load_fixtures(path)
        assert loaded == fixtures

    def test_load_rejects_non_array_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text('{"not": "a list"}', encoding="utf-8")
        try:
            load_fixtures(path)
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "expected a JSON array" in str(exc)
