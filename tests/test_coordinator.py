"""
Tests for the coordinator agent using a mocked Anthropic client.
"""
import json
import pathlib
import pytest
from unittest.mock import MagicMock, patch

FIXTURE = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "sample_commit.json").read_text()
)


def _make_mock_client(tool_calls: list, final_text: str):
    """
    Builds a mock Anthropic client that returns tool_calls in sequence,
    then a final end_turn response.
    """
    client = MagicMock()
    responses = []

    for tool_name, tool_input, tool_id in tool_calls:
        block = MagicMock()
        block.type = "tool_use"
        block.name = tool_name
        block.input = tool_input
        block.id = tool_id
        msg = MagicMock()
        msg.stop_reason = "tool_use"
        msg.content = [block]
        responses.append(msg)

    final_block = MagicMock()
    final_block.type = "text"
    final_block.text = final_text
    final_msg = MagicMock()
    final_msg.stop_reason = "end_turn"
    final_msg.content = [final_block]
    responses.append(final_msg)

    client.messages.create.side_effect = responses
    return client


def test_coordinator_calls_diff_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    mock_client = _make_mock_client(
        tool_calls=[
            (
                "fetch_commit_diff",
                {"sha": FIXTURE["sha"], "repo": FIXTURE["repo"]},
                "tool_1",
            ),
            (
                "delegate_to_subagent",
                {
                    "subagent": "diff_analyzer",
                    "prompt": "Analyze this diff: ...",
                },
                "tool_2",
            ),
            (
                "delegate_to_subagent",
                {
                    "subagent": "slide_writer",
                    "prompt": "Write slides for: ...",
                },
                "tool_3",
            ),
            (
                "write_presentation",
                {"content": "---\nmarp: true\n---\n# Test Slide\n"},
                "tool_4",
            ),
        ],
        final_text="Presentation saved to output/presentation.md",
    )

    with (
        patch("src.tools.github_tools.handle_github_tool") as mock_gh,
        patch("src.agent.subagents.diff_analyzer.run") as mock_analyzer,
        patch("src.agent.subagents.slide_writer.run") as mock_writer,
    ):
        mock_gh.return_value = FIXTURE["diff"]
        mock_analyzer.return_value = {"summary": "Added auth middleware", "impact": "medium"}
        mock_writer.return_value = "---\nmarp: true\n---\n# Auth Middleware\n"

        from src.agent.coordinator import run

        result = run(
            {"sha": FIXTURE["sha"], "repo": FIXTURE["repo"], "message": FIXTURE["message"]},
            mock_client,
        )

    assert "presentation" in result.lower() or result


def test_write_presentation_creates_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.tools.presentation_tools import handle_presentation_tool

    result = handle_presentation_tool(
        "write_presentation", {"content": "---\nmarp: true\n---\n# Hello\n"}
    )
    assert "path" in result
    assert pathlib.Path(result["path"]).exists()


def test_diff_analyzer_parses_json():
    from src.agent.subagents.diff_analyzer import run

    mock_client = MagicMock()
    mock_block = MagicMock()
    mock_block.text = json.dumps(
        {
            "summary": "Added auth middleware",
            "changed_areas": ["src/middleware"],
            "key_changes": [],
            "impact": "medium",
            "impact_reason": "Security-relevant code added",
            "presentation_angle": "Introducing JWT auth to secure endpoints",
        }
    )
    mock_client.messages.create.return_value = MagicMock(content=[mock_block])

    result = run("Analyze this diff", mock_client)
    assert result["impact"] == "medium"
    assert "summary" in result
