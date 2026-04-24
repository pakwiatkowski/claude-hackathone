"""
PreToolUse hard-stop hook.

check_pre_tool_use(tool_name, tool_input) -> (allowed: bool, deny_message: str)

Returns (True, "") if the call is permitted.
Returns (False, reason) if it must be blocked — the caller sends a deny
confirmation back to the agent and logs the pattern match.

This is a synchronous, deterministic gate — it does not call the LLM.
"""

import re
from typing import Any

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# SSN pattern — presence in non-PII-designated fields is a hard block
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Fields where SSN may legitimately appear (PII-designated)
_PII_DESIGNATED_FIELDS: set[str] = set()  # none in current tool set

# Prompt-injection / exfiltration patterns checked in ticket bodies
_EXFIL_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(prior|previous|above)\s+instructions", re.I),
    re.compile(r"route\s+(this\s+)?to\s+(the\s+)?ceo", re.I),
    re.compile(r"disregard\s+(your\s+)?(system\s+)?prompt", re.I),
    re.compile(r"you\s+are\s+now\s+a", re.I),
    re.compile(r"new\s+instructions?:", re.I),
    re.compile(r"print\s+(your\s+)?system\s+prompt", re.I),
]

# Tool name prefixes that are always blocked (financial/payroll guard)
_BLOCKED_TOOL_PREFIXES: tuple[str, ...] = ("payroll_", "finance_")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _contains_ssn(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_SSN_PATTERN.search(value))
    if isinstance(value, dict):
        return any(_contains_ssn(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_ssn(v) for v in value)
    return False


def _contains_exfil_pattern(text: str) -> bool:
    return any(p.search(text) for p in _EXFIL_PATTERNS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_pre_tool_use(
    tool_name: str, tool_input: dict[str, Any]
) -> tuple[bool, str]:
    """
    Returns (True, "") if the tool call is allowed.
    Returns (False, deny_message) if it must be hard-blocked.
    """

    # 1. Block forbidden tool name prefixes (payroll, finance)
    if tool_name.startswith(_BLOCKED_TOOL_PREFIXES):
        return (
            False,
            f"Tool '{tool_name}' is blocked. Payroll and financial system "
            "endpoints are outside the agent's authorised scope. Escalate to tier2.",
        )

    # 2. Block reset_password on frozen / terminated accounts
    if tool_name == "reset_password":
        user_id = tool_input.get("user_id", "")
        # Import here to avoid circular dependency; in prod use a shared account store
        from src.tools.password_reset_tools import _ACCOUNT_STORE

        account = _ACCOUNT_STORE.get(user_id, {})
        status = account.get("account_status", "")
        if status in ("frozen", "terminated"):
            return (
                False,
                f"Hard stop: reset_password blocked for user_id='{user_id}' "
                f"(account_status='{status}'). Route to Security team.",
            )

    # 3. Block any tool call containing SSN in non-PII-designated fields
    for field, value in tool_input.items():
        if field in _PII_DESIGNATED_FIELDS:
            continue
        if _contains_ssn(value):
            return (
                False,
                f"Hard stop: SSN pattern detected in field '{field}' of tool "
                f"'{tool_name}'. This call has been blocked and flagged for "
                "security review. Do not retry with PII in this field.",
            )

    # 4. Block route_ticket to security queue if prompt-injection pattern found in body
    if tool_name == "route_ticket":
        body = tool_input.get("body", "") or tool_input.get("notes", "")
        if body and _contains_exfil_pattern(body):
            return (
                False,
                "Hard stop: prompt-injection pattern detected in ticket body. "
                "Ticket has been hard-routed to the security queue for manual review. "
                "Do not process further.",
            )

    return True, ""
