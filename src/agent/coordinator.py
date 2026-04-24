"""
Coordinator agent: receives commit context, delegates analysis and slide writing
to specialist subagents, and assembles the final presentation.
"""
import anthropic
import json
from src.tools.github_tools import GITHUB_TOOLS, handle_github_tool
from src.tools.presentation_tools import PRESENTATION_TOOLS, handle_presentation_tool

COORDINATOR_SYSTEM = """
You are a presentation coordinator agent. Your job is to produce an engaging slide deck
every time code is committed to a GitHub repository.

When given commit metadata and a diff, you will:
1. Use the fetch_commit_diff tool to retrieve the full diff if not already provided.
2. Delegate to the diff_analyzer subagent to understand what changed and why it matters.
3. Delegate to the slide_writer subagent to turn that analysis into a Marp slide deck.
4. Use the write_presentation tool to save the finished slides.

Escalate (do NOT auto-generate a slide) if:
- The commit only changes generated files (lock files, dist/, build/).
- The diff is empty or the commit message starts with "chore(deps-update)" (automated bumps).

Always log your routing decision before delegating.
"""


def run(commit_info: dict, client: anthropic.Anthropic) -> str:
    """
    Runs the coordinator agent for a single commit.
    Returns the path to the written presentation file.
    """
    tools = GITHUB_TOOLS + PRESENTATION_TOOLS

    messages = [
        {
            "role": "user",
            "content": (
                f"New commit received. Please generate a presentation.\n\n"
                f"Commit info:\n{json.dumps(commit_info, indent=2)}"
            ),
        }
    ]

    while True:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            system=COORDINATOR_SYSTEM,
            tools=tools,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "Presentation generated."

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = _dispatch_tool(block.name, block.input, commit_info, client)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )
            messages.append({"role": "user", "content": tool_results})


def _dispatch_tool(name: str, inputs: dict, commit_info: dict, client: anthropic.Anthropic):
    if name in {t["name"] for t in GITHUB_TOOLS}:
        return handle_github_tool(name, inputs)
    if name in {t["name"] for t in PRESENTATION_TOOLS}:
        return handle_presentation_tool(name, inputs)
    if name == "delegate_to_subagent":
        return _delegate(inputs["subagent"], inputs["prompt"], client)
    return {"isError": True, "reason": f"Unknown tool: {name}"}


def _delegate(subagent: str, prompt: str, client: anthropic.Anthropic) -> dict:
    from src.agent.subagents.diff_analyzer import run as analyze
    from src.agent.subagents.slide_writer import run as write_slides

    if subagent == "diff_analyzer":
        return {"result": analyze(prompt, client)}
    if subagent == "slide_writer":
        return {"result": write_slides(prompt, client)}
    return {"isError": True, "reason": f"Unknown subagent: {subagent}"}
