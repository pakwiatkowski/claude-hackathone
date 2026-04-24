"""
SoftwareSpecialist subagent.

Receives only: ticket_id, user_id, issue_summary.
Has no access to coordinator context.
Runs: search_knowledge_base → check_software_entitlement → send_resolution → close_ticket.
On any isError tool response, or if no KB article is found, returns an escalation signal.
"""

import json
import os
from typing import Any

import anthropic

from src.config import MODEL
from src.hooks.pre_tool_use import check_pre_tool_use
from src.tools.software_tools import (
    SOFTWARE_TOOL_HANDLERS,
    SOFTWARE_TOOL_SCHEMAS,
)

SPECIALIST_SYSTEM_PROMPT = """\
You are the Software Support Specialist for the IT helpdesk.

Your job for each task:
1. Call search_knowledge_base with the issue description (and optionally the software name).
2. If total_found = 0: stop immediately and return:
   {"escalate": true, "reason": "NO_KB_MATCH"}
   Do not attempt to resolve without a KB article.
3. If articles are found: pick the best matching article (highest relevance to the issue).
4. Call check_software_entitlement with the user_id and the software name from the article.
5. If entitled=false: stop and return:
   {"escalate": true, "reason": "NOT_ENTITLED"}
6. If entitled=true: call send_resolution with the user_id, kb_article_id, and a short custom_message
   summarising what the user should do.
7. Call close_ticket with a brief resolution summary referencing the KB article used.

Rules you must follow:
- Never install, uninstall, or configure software directly.
- If any tool returns isError=true, stop immediately and return:
  {"escalate": true, "reason": "<reasonCode from the tool error>"}
- Close the ticket only after send_resolution confirms sent=True.
- Keep messages to the user concise and professional.
"""


def run_software_specialist(
    ticket_id: str,
    user_id: str,
    issue_summary: str,
) -> dict[str, Any]:
    """
    Run the SoftwareSpecialist for a single ticket.
    Returns a dict with keys: success, escalate, escalation_reason, resolution_summary.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

    task_prompt = (
        f"Ticket ID: {ticket_id}\n"
        f"User ID: {user_id}\n"
        f"Issue: {issue_summary}\n\n"
        "Please resolve this software issue following your instructions."
    )

    messages: list[dict] = [{"role": "user", "content": task_prompt}]

    result: dict[str, Any] = {
        "ticket_id": ticket_id,
        "user_id": user_id,
        "success": False,
        "escalate": False,
        "escalation_reason": None,
        "resolution_summary": None,
    }

    for _ in range(20):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SPECIALIST_SYSTEM_PROMPT,
            tools=SOFTWARE_TOOL_SCHEMAS,  # type: ignore[arg-type]
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    text = block.text.strip()
                    # Check if the model returned an escalation JSON
                    try:
                        start = text.find("{")
                        end = text.rfind("}") + 1
                        if start >= 0 and end > start:
                            import json as _json
                            decision = _json.loads(text[start:end])
                            if decision.get("escalate"):
                                result["escalate"] = True
                                result["escalation_reason"] = decision.get("reason", "UNKNOWN")
                                result["success"] = False
                                return result
                    except (ValueError, KeyError):
                        pass
                    result["resolution_summary"] = text
            result["success"] = not result["escalate"]
            break

        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                allowed, deny_msg = check_pre_tool_use(tool_name, tool_input)
                if not allowed:
                    result["escalate"] = True
                    result["escalation_reason"] = deny_msg
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(
                                {
                                    "isError": True,
                                    "reasonCode": "HARD_STOP",
                                    "guidance": deny_msg,
                                }
                            ),
                        }
                    )
                    continue

                handler = SOFTWARE_TOOL_HANDLERS.get(tool_name)
                if not handler:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(
                                {
                                    "isError": True,
                                    "reasonCode": "UNKNOWN_TOOL",
                                    "guidance": f"Tool '{tool_name}' is not available.",
                                }
                            ),
                        }
                    )
                    continue

                tool_output = handler(**tool_input)

                if tool_output.get("isError"):
                    result["escalate"] = True
                    result["escalation_reason"] = (
                        f"{tool_output.get('reasonCode')}: {tool_output.get('guidance')}"
                    )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_output),
                    }
                )

            messages.append({"role": "user", "content": tool_results})

            if result["escalate"]:
                result["success"] = False
                break

    return result
