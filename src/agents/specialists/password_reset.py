"""
PasswordResetSpecialist subagent.

Receives only: ticket_id, user_id, issue_summary.
Has no access to coordinator context.
Runs: lookup_account → verify_identity → reset_password → close_ticket.
On any isError tool response, returns an escalation signal.
"""

import json
import os
from typing import Any

import anthropic

from src.config import MODEL
from src.hooks.pre_tool_use import check_pre_tool_use
from src.tools.password_reset_tools import (
    PASSWORD_RESET_TOOL_HANDLERS,
    PASSWORD_RESET_TOOL_SCHEMAS,
)

SPECIALIST_SYSTEM_PROMPT = """\
You are the Password Reset Specialist for the IT helpdesk.

Your job for each task:
1. Call lookup_account to confirm the account is eligible (active or locked, not frozen/terminated).
2. Ask the user for their employee ID and security answer, then call verify_identity.
3. If verified=true, call reset_password with their preferred delivery method.
4. Call close_ticket with a brief resolution summary.

Rules you must follow:
- Never call reset_password before verify_identity returns verified=true.
- If any tool returns isError=true, stop immediately and return:
  {"escalate": true, "reason": "<reasonCode from the tool error>"}
- Never ask for passwords. Never log security answers.
- Close the ticket only after reset_password confirms success=true.
- Keep your messages to the user concise and professional.
"""


def run_password_reset_specialist(
    ticket_id: str,
    user_id: str,
    issue_summary: str,
) -> dict[str, Any]:
    """
    Run the PasswordResetSpecialist for a single ticket.
    Returns a dict with keys: success, escalate, escalation_reason, resolution_summary.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

    task_prompt = (
        f"Ticket ID: {ticket_id}\n"
        f"User ID: {user_id}\n"
        f"Issue: {issue_summary}\n\n"
        "Please help this user reset their password following your instructions."
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

    # Agentic loop — runs until end_turn or escalation
    for _ in range(20):  # hard ceiling to prevent runaway loops
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SPECIALIST_SYSTEM_PROMPT,
            tools=PASSWORD_RESET_TOOL_SCHEMAS,  # type: ignore[arg-type]
            messages=messages,
        )

        # Collect assistant turn
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Extract final text response as resolution summary
            for block in response.content:
                if hasattr(block, "text"):
                    result["resolution_summary"] = block.text
            result["success"] = not result["escalate"]
            break

        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                # Hard-stop check
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

                handler = PASSWORD_RESET_TOOL_HANDLERS.get(tool_name)
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

                # If the tool returned an error, set escalation flag
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

            # If escalation was triggered, exit the loop
            if result["escalate"]:
                result["success"] = False
                break

    return result
