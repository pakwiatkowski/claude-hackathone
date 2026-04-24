"""
Coordinator agent.

run_coordinator(ticket) → CoordinatorResult dict

Flow:
  1. classify_ticket (with validation-retry loop, up to MAX_RETRIES)
  2. lookup_user (account context)
  3. Decide: auto-resolve path OR route path
  4. Auto-resolve → spawn PasswordResetSpecialist
  5. Route → route_ticket + update_ticket
  6. update_ticket (always — audit log)
"""

import json
import os
from typing import Any

import anthropic
from pydantic import ValidationError

from src.config import CONFIDENCE_THRESHOLD, MAX_RETRIES, MODEL
from src.hooks.pre_tool_use import check_pre_tool_use
from src.models.schemas import TicketClassification
from src.tools.coordinator_tools import (
    COORDINATOR_TOOL_HANDLERS,
    COORDINATOR_TOOL_SCHEMAS,
)

# Lazy imports to avoid circular dependencies
def _get_password_reset_specialist():
    from src.agents.specialists.password_reset import run_password_reset_specialist
    return run_password_reset_specialist


def _get_networking_specialist():
    from src.agents.specialists.networking import run_networking_specialist
    return run_networking_specialist


def _get_software_specialist():
    from src.agents.specialists.software import run_software_specialist
    return run_software_specialist


COORDINATOR_SYSTEM_PROMPT = """\
You are the IT Helpdesk Coordinator. You process incoming support tickets end-to-end.

For every ticket you receive, you must:

1. Call classify_ticket with the ticket body, channel, and user_id.
   The result must conform to this schema:
   {
     "priority": "P1"|"P2"|"P3"|"P4",
     "category": "password_reset"|"network"|"hardware"|"software"|"security_incident"|"other",
     "confidence": 0.0–1.0,
     "reasoning": "<non-empty string>",
     "auto_resolvable": true|false
   }
   If the result is invalid, you will receive the specific validation error.
   Correct it and retry — do not give up until you have a valid classification
   or until you have retried 3 times.

2. Call lookup_user with the user_id to retrieve account context.

3. Decide routing:
   AUTO-RESOLVE path — ALL of the following must be true:
     - auto_resolvable = true
     - confidence >= 0.70
     - priority != "P1"
     - category IN ["password_reset", "network", "software"]
     - account_status != "frozen" and account_status != "terminated"
     - vip_flag = false OR priority in ["P3", "P4"]
   If all conditions met → respond with JSON:
     {"action": "auto_resolve", "ticket_id": "...", "user_id": "...", "issue_summary": "...", "category": "..."}

   ROUTE path — any condition above is false → call route_ticket, then respond with JSON:
     {"action": "routed", "queue": "...", "escalated": true|false, "escalation_reason": "..."|null}

4. Always call update_ticket at the end with your full reasoning chain, decision,
   retry_count, and error_types list. This is mandatory — never skip it.

Escalation rules (set escalated=true in route decision when any apply):
  - priority = "P1"
  - confidence < 0.70
  - category = "security_incident"
  - account_status = "frozen" or "terminated"
  - vip_flag = true AND priority in ["P1", "P2"]

Your reasoning_chain for update_ticket must be a JSON string of all steps taken,
e.g.: [{"step": "classify", "result": {...}}, {"step": "lookup_user", "result": {...}}, ...]
"""


def run_coordinator(ticket: dict[str, Any]) -> dict[str, Any]:
    """
    Process a single ticket through the coordinator.

    ticket keys: ticket_id, body, channel, user_id
    Returns a CoordinatorResult-shaped dict.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

    ticket_id = ticket["ticket_id"]
    ticket_message = (
        f"New support ticket:\n"
        f"Ticket ID: {ticket_id}\n"
        f"Channel: {ticket.get('channel', 'portal')}\n"
        f"User ID: {ticket.get('user_id', '')}\n"
        f"Body:\n{ticket.get('body', '')}"
    )

    messages: list[dict] = [{"role": "user", "content": ticket_message}]

    # Tracking state
    retry_count = 0
    error_types: list[str] = []
    reasoning_steps: list[dict] = []
    final_result: dict[str, Any] = {
        "ticket_id": ticket_id,
        "priority": "P3",
        "category": "other",
        "confidence": 0.0,
        "queue": None,
        "auto_resolved": False,
        "escalated": False,
        "escalation_reason": None,
        "retry_count": 0,
        "error_types": [],
        "reasoning_chain": "",
    }

    # Agentic loop
    for _ in range(30):  # hard ceiling
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=COORDINATOR_SYSTEM_PROMPT,
            tools=COORDINATOR_TOOL_SCHEMAS,  # type: ignore[arg-type]
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        # ---------------------------------------------------------------
        # end_turn — coordinator produced its final answer
        # ---------------------------------------------------------------
        if response.stop_reason == "end_turn":
            for block in response.content:
                if not hasattr(block, "text"):
                    continue
                text = block.text.strip()
                # Try to parse the coordinator's final JSON decision
                try:
                    # Extract JSON from potential surrounding text
                    start = text.find("{")
                    end = text.rfind("}") + 1
                    if start >= 0 and end > start:
                        decision = json.loads(text[start:end])
                        action = decision.get("action")

                        if action == "auto_resolve":
                            category = decision.get("category", final_result["category"])
                            specialist_kwargs = dict(
                                ticket_id=decision.get("ticket_id", ticket_id),
                                user_id=decision.get("user_id", ticket.get("user_id", "")),
                                issue_summary=decision.get("issue_summary", ticket.get("body", "")),
                            )
                            if category == "network":
                                specialist_result = _get_networking_specialist()(**specialist_kwargs)
                            elif category == "software":
                                specialist_result = _get_software_specialist()(**specialist_kwargs)
                            else:
                                # Default: password_reset (and any future categories added here)
                                specialist_result = _get_password_reset_specialist()(**specialist_kwargs)

                            final_result["auto_resolved"] = specialist_result.get("success", False)
                            final_result["escalated"] = specialist_result.get("escalate", False)
                            final_result["escalation_reason"] = specialist_result.get("escalation_reason")
                            if specialist_result.get("escalate"):
                                # Specialist hit a hard stop — route to tier2
                                from src.tools.coordinator_tools import route_ticket, update_ticket
                                route_ticket(ticket_id, "tier2", final_result["priority"], notify=True)
                                final_result["queue"] = "tier2"

                        elif action == "routed":
                            final_result["queue"] = decision.get("queue")
                            final_result["escalated"] = decision.get("escalated", False)
                            final_result["escalation_reason"] = decision.get("escalation_reason")

                except (json.JSONDecodeError, KeyError):
                    pass  # Coordinator text wasn't a decision JSON — that's fine

            break

        # ---------------------------------------------------------------
        # tool_use — execute tools
        # ---------------------------------------------------------------
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                # Hard-stop hook
                allowed, deny_msg = check_pre_tool_use(tool_name, tool_input)
                if not allowed:
                    reasoning_steps.append(
                        {"step": tool_name, "hard_stop": True, "reason": deny_msg}
                    )
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

                handler = COORDINATOR_TOOL_HANDLERS.get(tool_name)
                if not handler:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(
                                {
                                    "isError": True,
                                    "reasonCode": "UNKNOWN_TOOL",
                                    "guidance": f"Tool '{tool_name}' is not registered.",
                                }
                            ),
                        }
                    )
                    continue

                raw_output = handler(**tool_input)

                # -------------------------------------------------------
                # Validation-retry for classify_ticket
                # -------------------------------------------------------
                if tool_name == "classify_ticket" and not raw_output.get("isError"):
                    try:
                        classification = TicketClassification.model_validate(raw_output)
                        # Update final_result fields from valid classification
                        final_result["priority"] = classification.priority
                        final_result["category"] = classification.category
                        final_result["confidence"] = classification.confidence
                        reasoning_steps.append(
                            {"step": "classify_ticket", "result": raw_output, "retry_count": retry_count}
                        )
                    except ValidationError as exc:
                        retry_count += 1
                        error_msg = str(exc)
                        error_types.append(error_msg)
                        reasoning_steps.append(
                            {"step": "classify_ticket_retry", "error": error_msg, "attempt": retry_count}
                        )
                        # Feed specific error back so the model can correct
                        feedback = (
                            f"classify_ticket result failed schema validation "
                            f"(attempt {retry_count}/{MAX_RETRIES}): {error_msg}. "
                            "Please correct and retry."
                        )
                        if retry_count >= MAX_RETRIES:
                            raw_output = {
                                "isError": True,
                                "reasonCode": "VALIDATION_EXHAUSTED",
                                "guidance": (
                                    f"Classification failed schema validation after "
                                    f"{MAX_RETRIES} retries. Escalating to tier2."
                                ),
                            }
                            final_result["escalated"] = True
                            final_result["escalation_reason"] = "schema_validation_exhausted"
                        else:
                            raw_output = {"validation_error": feedback}
                else:
                    reasoning_steps.append({"step": tool_name, "result": raw_output})

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(raw_output),
                    }
                )

            messages.append({"role": "user", "content": tool_results})

    # ---------------------------------------------------------------
    # Finalise
    # ---------------------------------------------------------------
    final_result["retry_count"] = retry_count
    final_result["error_types"] = error_types
    final_result["reasoning_chain"] = json.dumps(reasoning_steps)

    # Write audit log to ticket store
    from src.tools.coordinator_tools import update_ticket

    decision_str = (
        "auto_resolved" if final_result["auto_resolved"]
        else ("escalated" if final_result["escalated"] else "routed")
    )
    update_ticket(
        ticket_id=ticket_id,
        reasoning_chain=final_result["reasoning_chain"],
        decision=decision_str,
        retry_count=retry_count,
        error_types=error_types,
    )

    return final_result
