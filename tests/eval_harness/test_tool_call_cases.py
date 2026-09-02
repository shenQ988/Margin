"""Dataset-shape validation for eval/tool_call_cases.py.

These assert the dataset itself meets its own stated coverage bar (>=15
cases, every stub tool covered at least once, >=3 negative, >=3 regression,
>=3 ambiguous) so a future edit that silently drops coverage fails loudly
here instead of only being noticed by eyeballing a diff.
"""

from __future__ import annotations

from eval.stub_tools import STUB_TOOL_NAMES
from eval.tool_call_cases import EVAL_CASES


def test_at_least_fifteen_cases():
    assert len(EVAL_CASES) >= 15


def test_case_ids_are_unique():
    ids = [case.id for case in EVAL_CASES]
    assert len(ids) == len(set(ids))


def test_every_stub_tool_covered_by_a_positive_case():
    positive_tools = {case.expected_tool for case in EVAL_CASES if case.expected_tool is not None}
    missing = STUB_TOOL_NAMES - positive_tools
    assert not missing, f"tools with no covering eval case: {sorted(missing)}"


def test_expected_tool_names_are_registered_or_none():
    """Catches typos: every non-None expected_tool must be a real stub tool."""
    for case in EVAL_CASES:
        if case.expected_tool is not None:
            assert case.expected_tool in STUB_TOOL_NAMES, (
                f"{case.id}: expected_tool={case.expected_tool!r} is not a registered stub tool"
            )


def test_at_least_three_negative_cases():
    negative = [case for case in EVAL_CASES if case.category == "negative"]
    assert len(negative) >= 3
    # "negative" category cases must always expect no tool call — that's
    # what makes them negative. (Some "ambiguous" cases also expect no
    # tool call, but are tagged "ambiguous" instead — see
    # test_ambiguous_cases_may_expect_either_a_tool_or_none below.)
    for case in negative:
        assert case.expected_tool is None, case.id


def test_at_least_three_regression_cases():
    regression = [case for case in EVAL_CASES if case.category == "regression"]
    assert len(regression) >= 3


def test_at_least_three_ambiguous_cases():
    ambiguous = [case for case in EVAL_CASES if case.category == "ambiguous"]
    assert len(ambiguous) >= 3


def test_ambiguous_cases_may_expect_either_a_tool_or_none():
    """Unlike "negative" cases (always expected_tool=None) and "positive"
    cases (always a specific tool), "ambiguous" cases intentionally cover
    both — some probe over-eager tool calling (expected_tool=None), others
    probe tool-selection confusion between two plausible tools."""
    ambiguous = [case for case in EVAL_CASES if case.category == "ambiguous"]
    assert any(case.expected_tool is None for case in ambiguous)
    assert any(case.expected_tool is not None for case in ambiguous)


def test_session_groups_have_at_least_two_cases_in_order():
    """A session_group only makes sense with >=2 cases sharing it — a
    lone case in a group is a copy-paste bug, not a real repeat scenario."""
    groups: dict[str, list[str]] = {}
    for case in EVAL_CASES:
        if case.session_group:
            groups.setdefault(case.session_group, []).append(case.id)
    for group, case_ids in groups.items():
        assert len(case_ids) >= 2, f"session_group {group!r} has only one case: {case_ids}"


def test_expected_tool_sequence_starts_with_expected_tool():
    """expected_tool must always describe the FIRST step — it's what
    drives the hard pass/fail metrics, so it can never disagree with a
    longer expected_tool_sequence's first element."""
    for case in EVAL_CASES:
        if case.expected_tool_sequence:
            assert case.expected_tool_sequence[0] == case.expected_tool, case.id


def test_expected_tool_sequence_entries_are_registered_tools():
    for case in EVAL_CASES:
        if case.expected_tool_sequence:
            for tool_name in case.expected_tool_sequence:
                assert tool_name in STUB_TOOL_NAMES, f"{case.id}: {tool_name!r}"


def test_no_tool_names_contain_dots():
    """Dotted names (e.g. 'weread.shelf') are rejected by real provider
    function-calling APIs — see the module docstring in tool_call_cases.py."""
    for case in EVAL_CASES:
        if case.expected_tool is not None:
            assert "." not in case.expected_tool, case.id
