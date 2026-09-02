"""Tests for the eval's self-contained stub tool registry."""

from __future__ import annotations

import pytest

from eval.stub_tools import STUB_TOOL_NAMES, RecordingStubTool, build_stub_registry


def test_registry_contains_exactly_the_expected_tool_names():
    registry = build_stub_registry()
    assert set(registry.tool_names) == STUB_TOOL_NAMES


def test_fresh_registry_per_call_does_not_share_call_recordings():
    """Each build_stub_registry() call must be independent — otherwise one
    eval run's tool-call recordings could leak into the next."""
    registry_a = build_stub_registry()
    registry_b = build_stub_registry()
    tool_a = registry_a.get("weread_shelf")
    tool_b = registry_b.get("weread_shelf")
    assert isinstance(tool_a, RecordingStubTool)
    assert isinstance(tool_b, RecordingStubTool)
    assert tool_a is not tool_b
    assert tool_a.calls is not tool_b.calls


async def test_stub_tool_records_call_and_returns_canned_response():
    tool = RecordingStubTool(
        "example_tool",
        "an example",
        {"type": "object", "properties": {}, "required": []},
        canned_response="CANNED",
    )
    result = await tool.execute(book_title="Sapiens")
    assert result == "CANNED"
    assert tool.calls == [{"book_title": "Sapiens"}]


def test_every_stub_tool_produces_a_valid_openai_schema():
    registry = build_stub_registry()
    definitions = registry.get_definitions()
    assert len(definitions) == len(STUB_TOOL_NAMES)
    for definition in definitions:
        assert definition["type"] == "function"
        function = definition["function"]
        assert function["name"] in STUB_TOOL_NAMES
        assert isinstance(function["description"], str) and function["description"]
        assert function["parameters"]["type"] == "object"


@pytest.mark.parametrize("name", sorted(STUB_TOOL_NAMES))
def test_tool_name_has_no_dot_and_is_provider_safe(name: str):
    """OpenAI/Anthropic function-calling names must match [a-zA-Z0-9_-]+."""
    assert all(ch.isalnum() or ch in "_-" for ch in name)
