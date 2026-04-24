"""
NetworkingSpecialist subagent.

Receives only: ticket_id, user_id, issue_summary.
Has no access to coordinator context.
Runs: check_vpn_status → get_user_connectivity_diagnostics → push_remediation_guide → close_ticket.
On any isError tool response, returns an escalation signal.
"""

import json
import os
from typing import Any

import anthropic

from src.config import MODEL
from src.hooks.pre_tool_use import check_pre_tool_use
from src.tools.networking_tools import (
    NETWORKING_TOOL_HANDLERS,
    NETWORKING_TOOL_SCHEMAS,
)

SPECIALIST_SYSTEM_PROMPT = """\
You are the Networking Specialist for the IT helpdesk.

Your job for each task:
1. Call check_vpn_status (no gateway_id) to get an overview of all gateway health.
2. Call get_user_connectivity_diagnostics with the user_id to see their specific state.
3. Based on what you find, choose the most accurate issue_type and call push_remediation_guide:
   - Gateway status is "degraded" or "down" → issue_type = "vpn_gateway_degraded"
   - User's vpn_client_version is outdated (below 5.1.2) → issue_type = "vpn_client_outdated"
   - User has recent_auth_failures > 1 → issue_type = "vpn_auth_failures"
   - None of the above → issue_type = "vpn_general"
4. Call close_ticket with a concise resolution summary.

Rules you must follow:
- Never modify network configuration, firewall rules, or gateway settings.
- If any tool returns isError=true, stop immediately and return:
  {"escalate": true, "reason": "<reasonCode from the tool error>"}
- Do not escalate for degraded gateways — send the guide and close the ticket.
  Only escalate if the gateway status is "down" AND active_connections = 0 (full outage).
- Close the ticket only after push_remediation_guide confirms sent=True.
- Keep messages to the user concise and professional.
"""


def run_networking_specialist(
    ticket_id: str,
    user_id: str,
    issue_summary: str,
) -> dict[str, Any]:
    """
    Run the NetworkingSpecialist for a single ticket.
    Returns a dict with keys: success, escalate, escalation_reason, resolution_summary.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

    task_prompt = (
        f"Ticket ID: {ticket_id}\n"
        f"User ID: {user_id}\n"
        f"Issue: {issue_summary}\n\n"
        "Please diagnose and resolve this networking issue following your instructions."
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
            tools=NETWORKING_TOOL_SCHEMAS,  # type: ignore[arg-type]
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
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

                handler = NETWORKING_TOOL_HANDLERS.get(tool_name)
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
