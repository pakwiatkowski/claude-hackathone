"""
SoftwareSpecialist tools.

All functions return dicts. Errors use the ToolError shape so the specialist
can recover gracefully (or signal escalation) without parsing strings.

Tool count: 4. See ADR-001.
"""

from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _tool_error(reason_code: str, guidance: str) -> dict[str, Any]:
    return {"isError": True, "reasonCode": reason_code, "guidance": guidance}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Stub data stores
# ---------------------------------------------------------------------------

# Knowledge base: article_id → article metadata + content
_KB_STORE: dict[str, dict] = {
    "KB-001": {
        "title": "Outlook crashes on startup — fix for error 0x800CCC0E",
        "software": "outlook",
        "keywords": ["outlook", "crash", "0x800ccc0e", "not opening", "email client"],
        "summary": (
            "Repair the Outlook profile: File → Account Settings → Email → Repair. "
            "If that fails, recreate the profile via Control Panel → Mail → Show Profiles → Add."
        ),
        "url": "https://intranet.acme.com/kb/KB-001",
    },
    "KB-002": {
        "title": "How to install Microsoft Teams on Windows 11",
        "software": "teams",
        "keywords": ["teams", "install", "microsoft teams", "download", "chat"],
        "summary": (
            "Open Software Center → search 'Microsoft Teams' → click Install. "
            "If not available, contact IT with your manager's approval for a license."
        ),
        "url": "https://intranet.acme.com/kb/KB-002",
    },
    "KB-003": {
        "title": "Excel crashes or freezes during large file operations",
        "software": "excel",
        "keywords": ["excel", "crash", "freeze", "spreadsheet", "not responding"],
        "summary": (
            "Disable hardware acceleration: File → Options → Advanced → uncheck "
            "'Disable hardware graphics acceleration'. Save and restart Excel."
        ),
        "url": "https://intranet.acme.com/kb/KB-003",
    },
    "KB-004": {
        "title": "How to update any software via Software Center",
        "software": "general",
        "keywords": ["update", "upgrade", "software center", "install update", "patch"],
        "summary": (
            "Open Software Center from the Start Menu. "
            "Go to 'Updates' tab — available updates are listed there. "
            "Select the software and click 'Install'."
        ),
        "url": "https://intranet.acme.com/kb/KB-004",
    },
    "KB-005": {
        "title": "Application shows 'License expired' or 'Not activated' error",
        "software": "general",
        "keywords": ["license", "expired", "not activated", "activation", "error"],
        "summary": (
            "Sign out and back in to the application using your corporate SSO credentials. "
            "If the issue persists, IT will need to reactivate your license — "
            "escalation to tier1 is required."
        ),
        "url": "https://intranet.acme.com/kb/KB-005",
    },
}

# Software entitlement store: user_id → list of entitled software names
_ENTITLEMENT_STORE: dict[str, dict] = {
    "U-001": {
        "entitled_software": ["outlook", "excel", "teams", "word", "powerpoint"],
        "department_tier": "standard",
    },
    "U-002": {
        "entitled_software": ["outlook", "excel", "teams", "word", "powerpoint", "project", "visio"],
        "department_tier": "finance",
    },
    "U-003": {
        "entitled_software": ["outlook", "excel", "teams", "word"],
        "department_tier": "standard",
    },
    "U-999": {
        "entitled_software": [],
        "department_tier": "suspended",
    },
}

# Notification log
_NOTIFICATION_LOG: list[dict] = []

# Ticket store
_TICKET_STORE: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Tool 1: search_knowledge_base
# ---------------------------------------------------------------------------

SEARCH_KNOWLEDGE_BASE_SCHEMA = {
    "name": "search_knowledge_base",
    "description": (
        "Search the IT knowledge base for articles matching a query. "
        "Returns a list of matching articles with their IDs, titles, summaries, and URLs. "
        "Optionally filter by software_name to narrow results. "
        "Does NOT install, configure, or modify any software. "
        "Does NOT guarantee a match — check if results list is empty before proceeding. "
        "Query should be the user's plain-language description of the issue, "
        "e.g. 'Outlook crashes on startup' or 'how to install Teams'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Plain-language description of the software issue.",
            },
            "software_name": {
                "type": "string",
                "description": (
                    "Optional software name to filter results "
                    "(e.g. 'outlook', 'teams', 'excel'). "
                    "Use 'general' for non-specific software questions."
                ),
            },
        },
        "required": ["query"],
    },
}


def search_knowledge_base(query: str, software_name: str | None = None) -> dict[str, Any]:
    if not query.strip():
        return _tool_error("EMPTY_QUERY", "Query cannot be empty.")

    query_lower = query.lower()
    results = []

    for article_id, article in _KB_STORE.items():
        # Filter by software if provided
        if software_name and article["software"] not in (software_name.lower(), "general"):
            continue

        # Keyword match score
        score = sum(1 for kw in article["keywords"] if kw in query_lower)
        if score > 0:
            results.append(
                {
                    "article_id": article_id,
                    "title": article["title"],
                    "software": article["software"],
                    "summary": article["summary"],
                    "url": article["url"],
                    "match_score": score,
                }
            )

    results.sort(key=lambda x: x["match_score"], reverse=True)
    # Remove internal score from response
    for r in results:
        del r["match_score"]

    return {
        "query": query,
        "results": results,
        "total_found": len(results),
    }


# ---------------------------------------------------------------------------
# Tool 2: check_software_entitlement
# ---------------------------------------------------------------------------

CHECK_SOFTWARE_ENTITLEMENT_SCHEMA = {
    "name": "check_software_entitlement",
    "description": (
        "Verify whether a user is licensed and entitled to use a specific software application. "
        "Returns entitled=true/false and the user's department tier. "
        "Does NOT grant or revoke licenses. "
        "Does NOT access financial or payroll records. "
        "Input: user_id (e.g. 'U-001') and software_name (e.g. 'outlook', 'teams', 'excel'). "
        "If entitled=false, escalate to tier1 — do not auto-resolve."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier (e.g. U-001).",
            },
            "software_name": {
                "type": "string",
                "description": "Lowercase software name to check (e.g. 'outlook', 'teams').",
            },
        },
        "required": ["user_id", "software_name"],
    },
}


def check_software_entitlement(user_id: str, software_name: str) -> dict[str, Any]:
    entitlement = _ENTITLEMENT_STORE.get(user_id)
    if not entitlement:
        return _tool_error(
            "USER_NOT_FOUND",
            f"No entitlement record for user_id='{user_id}'. Escalate to tier1.",
        )

    if entitlement["department_tier"] == "suspended":
        return _tool_error(
            "ACCOUNT_SUSPENDED",
            f"User '{user_id}' account is suspended. Cannot check or grant entitlements.",
        )

    entitled = software_name.lower() in entitlement["entitled_software"]

    return {
        "user_id": user_id,
        "software_name": software_name.lower(),
        "entitled": entitled,
        "department_tier": entitlement["department_tier"],
        "entitled_software_count": len(entitlement["entitled_software"]),
    }


# ---------------------------------------------------------------------------
# Tool 3: send_resolution
# ---------------------------------------------------------------------------

SEND_RESOLUTION_SCHEMA = {
    "name": "send_resolution",
    "description": (
        "Deliver a KB article link and optional custom message to the user's registered channel. "
        "Use this after search_knowledge_base returns a matching article "
        "and check_software_entitlement confirms the user is entitled. "
        "Does NOT directly install or uninstall software. "
        "Does NOT send if no article_id is provided. "
        "Does NOT resolve the ticket — call close_ticket separately after this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier (e.g. U-001).",
            },
            "kb_article_id": {
                "type": "string",
                "description": "Article ID from search_knowledge_base (e.g. 'KB-001').",
            },
            "custom_message": {
                "type": "string",
                "description": (
                    "Optional additional context or personalised instructions "
                    "to include alongside the KB article."
                ),
            },
        },
        "required": ["user_id", "kb_article_id"],
    },
}


def send_resolution(
    user_id: str,
    kb_article_id: str,
    custom_message: str | None = None,
) -> dict[str, Any]:
    article = _KB_STORE.get(kb_article_id)
    if not article:
        return _tool_error(
            "ARTICLE_NOT_FOUND",
            f"No KB article with id='{kb_article_id}'. "
            "Run search_knowledge_base first to get a valid article ID.",
        )

    message_parts = [
        f"Hi, here's a knowledge base article that should help with your issue:",
        f"**{article['title']}**",
        article["summary"],
        f"Full article: {article['url']}",
    ]
    if custom_message:
        message_parts.append(f"\nAdditional note: {custom_message}")

    full_message = "\n\n".join(message_parts)

    entry = {
        "user_id": user_id,
        "kb_article_id": kb_article_id,
        "message_sent": full_message,
        "sent_at": _now_iso(),
        "channel": "email",
    }
    _NOTIFICATION_LOG.append(entry)

    return {
        "sent": True,
        "user_id": user_id,
        "kb_article_id": kb_article_id,
        "article_title": article["title"],
        "channel": "email",
        "sent_at": entry["sent_at"],
    }


# ---------------------------------------------------------------------------
# Tool 4: close_ticket
# ---------------------------------------------------------------------------

CLOSE_TICKET_SCHEMA = {
    "name": "close_ticket",
    "description": (
        "Mark a ticket as resolved and write a resolution summary. "
        "Call this only after send_resolution has returned sent=True. "
        "Does NOT escalate or re-route — if something went wrong use the "
        "escalation signal instead of calling this tool."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "resolution_summary": {
                "type": "string",
                "description": "Plain-text summary of what was done, including KB article referenced.",
            },
            "auto_resolved": {
                "type": "boolean",
                "description": "True if resolved without human intervention.",
            },
        },
        "required": ["ticket_id", "resolution_summary", "auto_resolved"],
    },
}


def close_ticket(ticket_id: str, resolution_summary: str, auto_resolved: bool) -> dict[str, Any]:
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

SOFTWARE_TOOL_SCHEMAS = [
    SEARCH_KNOWLEDGE_BASE_SCHEMA,
    CHECK_SOFTWARE_ENTITLEMENT_SCHEMA,
    SEND_RESOLUTION_SCHEMA,
    CLOSE_TICKET_SCHEMA,
]

SOFTWARE_TOOL_HANDLERS: dict[str, Any] = {
    "search_knowledge_base": search_knowledge_base,
    "check_software_entitlement": check_software_entitlement,
    "send_resolution": send_resolution,
    "close_ticket": close_ticket,
}
