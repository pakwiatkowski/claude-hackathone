"""
PasswordResetSpecialist tools.

All functions return dicts. Errors use the ToolError shape so the specialist
can recover gracefully (or signal escalation) without parsing strings.

Tool count: 4. See ADR-001.
"""

import secrets
import string
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _tool_error(reason_code: str, guidance: str) -> dict[str, Any]:
    return {"isError": True, "reasonCode": reason_code, "guidance": guidance}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_temp_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# Stub data stores
# ---------------------------------------------------------------------------

_ACCOUNT_STORE: dict[str, dict] = {
    "U-001": {
        "account_status": "active",
        "last_login": "2026-04-22T14:30:00Z",
        "failed_attempts": 0,
        "locked_since": None,
        "employee_id": "EMP-001",
        "security_answer_hash": "hashed:fluffy",  # answer: "fluffy"
    },
    "U-003": {
        "account_status": "locked",
        "last_login": "2026-04-23T09:00:00Z",
        "failed_attempts": 5,
        "locked_since": "2026-04-24T08:15:00Z",
        "employee_id": "EMP-003",
        "security_answer_hash": "hashed:sunshine",
    },
    "U-999": {
        "account_status": "frozen",
        "last_login": "2026-03-01T00:00:00Z",
        "failed_attempts": 0,
        "locked_since": None,
        "employee_id": "EMP-999",
        "security_answer_hash": "hashed:unknown",
    },
}

# Tracks which users have passed identity verification this session
_VERIFIED_USERS: set[str] = set()

# Simulated ticket store (shared reference with coordinator_tools)
_TICKET_STORE: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Tool 1: lookup_account
# ---------------------------------------------------------------------------

LOOKUP_ACCOUNT_SCHEMA = {
    "name": "lookup_account",
    "description": (
        "Retrieve the account status and lock metadata for a user. "
        "Returns account_status (active/locked/frozen/terminated), "
        "last_login, failed_attempts, and locked_since timestamp. "
        "Does NOT return passwords, security answers, or credentials of any kind. "
        "Returns ACCOUNT_FROZEN error if status is frozen or terminated — "
        "those accounts must not be touched by this specialist."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User identifier (e.g. U-001)."}
        },
        "required": ["user_id"],
    },
}


def lookup_account(user_id: str) -> dict[str, Any]:
    account = _ACCOUNT_STORE.get(user_id)
    if not account:
        return _tool_error(
            "ACCOUNT_NOT_FOUND",
            f"No account record for user_id='{user_id}'. Escalate to tier2.",
        )

    status = account["account_status"]
    if status in ("frozen", "terminated"):
        return _tool_error(
            "ACCOUNT_FROZEN",
            (
                f"Account for user_id='{user_id}' has status='{status}'. "
                "Password reset is not permitted for frozen/terminated accounts. "
                "Escalate to the Security team immediately."
            ),
        )

    return {
        "user_id": user_id,
        "account_status": status,
        "last_login": account["last_login"],
        "failed_attempts": account["failed_attempts"],
        "locked_since": account["locked_since"],
    }


# ---------------------------------------------------------------------------
# Tool 2: verify_identity
# ---------------------------------------------------------------------------

VERIFY_IDENTITY_SCHEMA = {
    "name": "verify_identity",
    "description": (
        "Verify the user's identity via employee ID and security challenge answer. "
        "Both must match the directory record for verification to succeed. "
        "Does NOT bypass verification on a partial match. "
        "Does NOT log or store the security_answer in any persistent record. "
        "Must be called before reset_password — reset will fail without it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "employee_id": {
                "type": "string",
                "description": "Employee ID provided by the user (e.g. EMP-001).",
            },
            "security_answer": {
                "type": "string",
                "description": "Answer to the user's security challenge question.",
            },
        },
        "required": ["user_id", "employee_id", "security_answer"],
    },
}


def verify_identity(user_id: str, employee_id: str, security_answer: str) -> dict[str, Any]:
    account = _ACCOUNT_STORE.get(user_id)
    if not account:
        return _tool_error(
            "ACCOUNT_NOT_FOUND",
            f"No account record for user_id='{user_id}'.",
        )

    # Employee ID check
    if account["employee_id"] != employee_id:
        return {
            "verified": False,
            "method_used": "employee_id+security_answer",
            "failure_reason": "Employee ID does not match directory record.",
        }

    # Security answer check (stub: compare to known hash pattern)
    expected_hash = account["security_answer_hash"]
    # In prod this would use a real hash comparison; stub checks the suffix
    expected_answer = expected_hash.replace("hashed:", "")
    if security_answer.strip().lower() != expected_answer:
        return {
            "verified": False,
            "method_used": "employee_id+security_answer",
            "failure_reason": "Security answer does not match.",
        }

    _VERIFIED_USERS.add(user_id)
    return {"verified": True, "method_used": "employee_id+security_answer"}


# ---------------------------------------------------------------------------
# Tool 3: reset_password
# ---------------------------------------------------------------------------

RESET_PASSWORD_SCHEMA = {
    "name": "reset_password",
    "description": (
        "Generate temporary credentials and deliver them to the user. "
        "Requires verify_identity to have been called and succeeded first — "
        "will return IDENTITY_NOT_VERIFIED if not. "
        "Will return ACCOUNT_NOT_ELIGIBLE if account is frozen or terminated. "
        "Delivery methods: 'email' (reset link to registered address) or "
        "'sms' (temp password to registered mobile). "
        "Does NOT reveal the temp password in the tool response — it is sent "
        "directly to the user's registered contact."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "delivery_method": {
                "type": "string",
                "enum": ["email", "sms"],
                "description": "How to deliver the temporary credentials.",
            },
        },
        "required": ["user_id", "delivery_method"],
    },
}


def reset_password(user_id: str, delivery_method: str) -> dict[str, Any]:
    if user_id not in _VERIFIED_USERS:
        return _tool_error(
            "IDENTITY_NOT_VERIFIED",
            (
                "verify_identity must be called and return verified=True before "
                "reset_password can be used. Do not proceed without verification."
            ),
        )

    account = _ACCOUNT_STORE.get(user_id)
    if not account:
        return _tool_error("ACCOUNT_NOT_FOUND", f"No account for user_id='{user_id}'.")

    status = account["account_status"]
    if status in ("frozen", "terminated"):
        return _tool_error(
            "ACCOUNT_NOT_ELIGIBLE",
            f"Account status='{status}'. Reset is not permitted. Escalate to Security.",
        )

    # Generate credentials (not returned in response — sent to user directly)
    _temp_password = _generate_temp_password()
    expiry_minutes = 60

    # Update account state
    account["account_status"] = "active"
    account["failed_attempts"] = 0
    account["locked_since"] = None

    return {
        "success": True,
        "user_id": user_id,
        "delivery_method": delivery_method,
        "temp_credential_sent": True,
        "expiry_minutes": expiry_minutes,
        "reset_at": _now_iso(),
        "note": "User must change password on next login.",
    }


# ---------------------------------------------------------------------------
# Tool 4: close_ticket
# ---------------------------------------------------------------------------

CLOSE_TICKET_SCHEMA = {
    "name": "close_ticket",
    "description": (
        "Mark a ticket as resolved and write a resolution summary. "
        "Call this only after reset_password has returned success=True. "
        "Does NOT escalate or re-route — if something went wrong use the "
        "escalation signal instead of calling this tool."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "resolution_summary": {
                "type": "string",
                "description": "Plain-text summary of what was done.",
            },
            "auto_resolved": {
                "type": "boolean",
                "description": "True if resolved without human intervention.",
            },
        },
        "required": ["ticket_id", "resolution_summary", "auto_resolved"],
    },
}


def close_ticket(
    ticket_id: str, resolution_summary: str, auto_resolved: bool
) -> dict[str, Any]:
    _TICKET_STORE.setdefault(ticket_id, {}).update(
        {
            "status": "resolved",
            "resolution_summary": resolution_summary,
            "auto_resolved": auto_resolved,
            "closed_at": _now_iso(),
        }
    )
    return {
        "closed": True,
        "ticket_id": ticket_id,
        "timestamp": _TICKET_STORE[ticket_id]["closed_at"],
    }


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

PASSWORD_RESET_TOOL_SCHEMAS = [
    LOOKUP_ACCOUNT_SCHEMA,
    VERIFY_IDENTITY_SCHEMA,
    RESET_PASSWORD_SCHEMA,
    CLOSE_TICKET_SCHEMA,
]

PASSWORD_RESET_TOOL_HANDLERS: dict[str, Any] = {
    "lookup_account": lookup_account,
    "verify_identity": verify_identity,
    "reset_password": reset_password,
    "close_ticket": close_ticket,
}
