"""
Coordinator agent tools.

All functions accept plain Python dicts (the SDK passes tool inputs as dicts)
and return dicts. On failure, return a ToolError-shaped dict so the agent can
recover without parsing an unstructured string.

Tool count: 4. Deliberately not expanded — see ADR-001.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any

from src.config import QUEUE_SLA_HOURS, SLA_HOURS

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _tool_error(reason_code: str, guidance: str) -> dict[str, Any]:
    return {"isError": True, "reasonCode": reason_code, "guidance": guidance}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Stub data store (replaces real ITSM/AD integration)
# ---------------------------------------------------------------------------

_TICKET_STORE: dict[str, dict] = {}

_USER_STORE: dict[str, dict] = {
    "U-001": {
        "email": "alice.smith@acme.com",
        "display_name": "Alice Smith",
        "department": "Engineering",
        "manager_id": "U-100",
        "account_status": "active",
        "vip_flag": False,
    },
    "U-002": {
        "email": "bob.jones@acme.com",
        "display_name": "Bob Jones",
        "department": "Finance",
        "manager_id": "U-101",
        "account_status": "active",
        "vip_flag": True,
    },
    "U-003": {
        "email": "carol.white@acme.com",
        "display_name": "Carol White",
        "department": "HR",
        "manager_id": "U-102",
        "account_status": "locked",
        "vip_flag": False,
    },
    "U-999": {
        "email": "dave.frost@acme.com",
        "display_name": "Dave Frost",
        "department": "IT",
        "manager_id": "U-100",
        "account_status": "frozen",
        "vip_flag": False,
    },
}

# ---------------------------------------------------------------------------
# Tool 1: classify_ticket
# ---------------------------------------------------------------------------

# Keyword signals used by the stub classifier
_CATEGORY_SIGNALS: dict[str, list[str]] = {
    "password_reset": ["password", "locked out", "can't log in", "reset", "forgot password", "account locked"],
    "network": ["vpn", "wifi", "network", "internet", "connectivity", "can't connect", "slow network"],
    "hardware": ["laptop", "monitor", "keyboard", "mouse", "printer", "hardware", "broken screen"],
    "software": ["install", "software", "app", "application", "update", "crash", "error"],
    "security_incident": ["phishing", "malware", "virus", "breach", "suspicious", "ransomware", "unauthorized"],
}

_PRIORITY_SIGNALS: dict[str, list[str]] = {
    "P1": ["outage", "down", "critical", "all users", "production", "entire company", "no one can"],
    "P2": ["urgent", "multiple users", "several users", "team can't", "department"],
    "P4": ["low priority", "when you get a chance", "no rush", "whenever"],
}

# Signals that make a network ticket auto-resolvable (VPN user-side issues)
_NETWORK_AUTO_RESOLVE_SIGNALS: list[str] = [
    "vpn", "is vpn down", "can't connect vpn", "vpn not working",
    "vpn not connecting", "vpn slow", "cannot connect to vpn",
]

# Signals that make a software ticket auto-resolvable (KB-lookupable issues)
_SOFTWARE_AUTO_RESOLVE_SIGNALS: list[str] = [
    "install", "how to", "error code", "crash", "not opening",
    "update", "freeze", "not responding", "won't open", "keeps crashing",
]


def _classify_body(body: str) -> tuple[str, str, float, bool]:
    """Returns (priority, category, confidence, auto_resolvable)."""
    body_lower = body.lower()

    # Category
    category_scores: dict[str, int] = {}
    for cat, signals in _CATEGORY_SIGNALS.items():
        category_scores[cat] = sum(1 for s in signals if s in body_lower)
    category = max(category_scores, key=category_scores.get)  # type: ignore[arg-type]
    cat_score = category_scores[category]
    if cat_score == 0:
        category = "other"

    # Priority
    priority = "P3"  # default
    for pri, signals in _PRIORITY_SIGNALS.items():
        if any(s in body_lower for s in signals):
            priority = pri
            break

    # Confidence: rough heuristic based on signal strength
    confidence = min(0.5 + cat_score * 0.15, 0.95) if cat_score > 0 else 0.45

    # Auto-resolvable per mandate:
    # - password_reset: always (excluding P1)
    # - network: only for VPN user-side issues (excluding P1)
    # - software: only when issue matches a KB-lookupable pattern (excluding P1)
    if priority == "P1":
        auto_resolvable = False
    elif category == "password_reset":
        auto_resolvable = True
    elif category == "network":
        auto_resolvable = any(s in body_lower for s in _NETWORK_AUTO_RESOLVE_SIGNALS)
    elif category == "software":
        auto_resolvable = any(s in body_lower for s in _SOFTWARE_AUTO_RESOLVE_SIGNALS)
    else:
        auto_resolvable = False

    return priority, category, confidence, auto_resolvable


CLASSIFY_TICKET_SCHEMA = {
    "name": "classify_ticket",
    "description": (
        "Classify an incoming IT helpdesk ticket. Returns priority (P1–P4), "
        "category, confidence score, a brief reasoning string, and whether the "
        "ticket is auto-resolvable without human intervention. "
        "Does NOT classify from ticket number alone. Does NOT process attachments."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "body": {
                "type": "string",
                "description": "Full text of the ticket or message.",
            },
            "channel": {
                "type": "string",
                "enum": ["jira", "slack", "portal", "email"],
                "description": "Channel the ticket arrived from.",
            },
            "user_id": {
                "type": "string",
                "description": "ID of the submitting user (e.g. U-001).",
            },
        },
        "required": ["body", "channel", "user_id"],
    },
}


def classify_ticket(body: str, channel: str, user_id: str) -> dict[str, Any]:
    if not body.strip():
        return _tool_error("EMPTY_BODY", "Ticket body is empty. Cannot classify without content.")

    priority, category, confidence, auto_resolvable = _classify_body(body)

    reasoning_parts = [f"Channel: {channel}."]
    for cat, signals in _CATEGORY_SIGNALS.items():
        matched = [s for s in signals if s in body.lower()]
        if matched:
            reasoning_parts.append(f"Category signals for '{cat}': {matched}.")
    reasoning_parts.append(f"Assigned category='{category}', priority='{priority}', confidence={confidence:.2f}.")

    return {
        "priority": priority,
        "category": category,
        "confidence": confidence,
        "reasoning": " ".join(reasoning_parts),
        "auto_resolvable": auto_resolvable,
    }


# ---------------------------------------------------------------------------
# Tool 2: lookup_user
# ---------------------------------------------------------------------------

LOOKUP_USER_SCHEMA = {
    "name": "lookup_user",
    "description": (
        "Look up an IT directory entry for a user. Returns email, display name, "
        "department, manager ID, account status, and VIP flag. "
        "Does NOT return payroll data, salary, financial records, or PII beyond "
        "directory fields. Input: user_id string (e.g. 'U-001')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier from the directory (e.g. U-001).",
            }
        },
        "required": ["user_id"],
    },
}


def lookup_user(user_id: str) -> dict[str, Any]:
    user = _USER_STORE.get(user_id)
    if not user:
        return _tool_error(
            "USER_NOT_FOUND",
            f"No directory entry for user_id='{user_id}'. Verify the ID and retry.",
        )
    return dict(user)


# ---------------------------------------------------------------------------
# Tool 3: route_ticket
# ---------------------------------------------------------------------------

ROUTE_TICKET_SCHEMA = {
    "name": "route_ticket",
    "description": (
        "Assign a ticket to a helpdesk queue and set its SLA timestamp. "
        "Valid queues: tier1, tier2, networking, security, hardware. "
        "Does NOT close or resolve the ticket — only assigns it. "
        "Does NOT send user notifications directly; set notify=true to trigger "
        "an automated acknowledgement email."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "queue": {
                "type": "string",
                "enum": ["tier1", "tier2", "networking", "security", "hardware"],
            },
            "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
            "notify": {
                "type": "boolean",
                "description": "Send acknowledgement notification to the submitting user.",
                "default": True,
            },
        },
        "required": ["ticket_id", "queue", "priority"],
    },
}


def route_ticket(
    ticket_id: str, queue: str, priority: str, notify: bool = True
) -> dict[str, Any]:
    if queue not in QUEUE_SLA_HOURS:
        return _tool_error(
            "INVALID_QUEUE",
            f"Queue '{queue}' is not valid. Choose from: {list(QUEUE_SLA_HOURS.keys())}.",
        )
    if priority not in SLA_HOURS:
        return _tool_error(
            "INVALID_PRIORITY",
            f"Priority '{priority}' is not valid. Choose from P1, P2, P3, P4.",
        )

    sla_hours = min(SLA_HOURS[priority], QUEUE_SLA_HOURS[queue])
    ticket_record = _TICKET_STORE.setdefault(ticket_id, {})
    ticket_record.update(
        {
            "queue": queue,
            "priority": priority,
            "routed_at": _now_iso(),
            "sla_hours": sla_hours,
            "status": "in_progress",
        }
    )

    return {
        "routed": True,
        "queue": queue,
        "priority": priority,
        "estimated_sla_hours": sla_hours,
        "notification_sent": notify,
        "routed_at": ticket_record["routed_at"],
    }


# ---------------------------------------------------------------------------
# Tool 4: update_ticket
# ---------------------------------------------------------------------------

UPDATE_TICKET_SCHEMA = {
    "name": "update_ticket",
    "description": (
        "Write the coordinator's reasoning chain, final decision, and retry "
        "metadata to the ticket record. Every ticket must have this called "
        "before the coordinator session ends — it is the audit log. "
        "Does NOT make routing decisions. Does NOT change ticket status."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "reasoning_chain": {
                "type": "string",
                "description": "JSON-serialisable string of all intermediate reasoning steps.",
            },
            "decision": {
                "type": "string",
                "description": "One of: auto_resolved, routed, escalated.",
                "enum": ["auto_resolved", "routed", "escalated"],
            },
            "retry_count": {
                "type": "integer",
                "description": "Number of classification retries before a valid result.",
                "minimum": 0,
            },
            "error_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of validation error messages from retry attempts.",
            },
        },
        "required": ["ticket_id", "reasoning_chain", "decision", "retry_count", "error_types"],
    },
}


def update_ticket(
    ticket_id: str,
    reasoning_chain: str,
    decision: str,
    retry_count: int,
    error_types: list[str],
) -> dict[str, Any]:
    ticket_record = _TICKET_STORE.setdefault(ticket_id, {})
    ticket_record["reasoning_chain"] = reasoning_chain
    ticket_record["decision"] = decision
    ticket_record["retry_count"] = retry_count
    ticket_record["error_types"] = error_types
    ticket_record["updated_at"] = _now_iso()

    return {"updated": True, "timestamp": ticket_record["updated_at"]}


# ---------------------------------------------------------------------------
# Tool registry (used by coordinator agent)
# ---------------------------------------------------------------------------

COORDINATOR_TOOL_SCHEMAS = [
    CLASSIFY_TICKET_SCHEMA,
    LOOKUP_USER_SCHEMA,
    ROUTE_TICKET_SCHEMA,
    UPDATE_TICKET_SCHEMA,
]

COORDINATOR_TOOL_HANDLERS: dict[str, Any] = {
    "classify_ticket": classify_ticket,
    "lookup_user": lookup_user,
    "route_ticket": route_ticket,
    "update_ticket": update_ticket,
}
