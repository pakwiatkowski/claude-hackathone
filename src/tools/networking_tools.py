"""
NetworkingSpecialist tools.

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

# VPN gateway monitoring state
_VPN_GATEWAY_STORE: dict[str, dict] = {
    "gw-us-east-1": {
        "status": "healthy",
        "active_connections": 312,
        "last_checked": "2026-04-24T10:00:00Z",
        "latency_ms": 18,
        "region": "US East",
    },
    "gw-eu-west-1": {
        "status": "degraded",
        "active_connections": 45,
        "last_checked": "2026-04-24T10:01:00Z",
        "latency_ms": 420,
        "region": "EU West",
    },
    "gw-ap-southeast-1": {
        "status": "healthy",
        "active_connections": 98,
        "last_checked": "2026-04-24T10:00:00Z",
        "latency_ms": 32,
        "region": "Asia Pacific",
    },
}

# Default gateway for each user (stub: in prod derived from HR location)
_USER_GATEWAY_MAP: dict[str, str] = {
    "U-001": "gw-us-east-1",
    "U-002": "gw-us-east-1",
    "U-003": "gw-eu-west-1",
    "U-999": "gw-us-east-1",
}

# User connectivity diagnostics
_USER_CONNECTIVITY_STORE: dict[str, dict] = {
    "U-001": {
        "last_vpn_auth": "2026-04-24T09:45:00Z",
        "last_seen_ip": "10.0.1.42",
        "vpn_client_version": "5.1.2",
        "recent_auth_failures": 0,
        "assigned_gateway": "gw-us-east-1",
        "client_os": "Windows 11",
    },
    "U-002": {
        "last_vpn_auth": "2026-04-23T17:30:00Z",
        "last_seen_ip": "10.0.1.77",
        "vpn_client_version": "5.0.9",
        "recent_auth_failures": 2,
        "assigned_gateway": "gw-us-east-1",
        "client_os": "macOS 14",
    },
    "U-003": {
        "last_vpn_auth": "2026-04-24T08:00:00Z",
        "last_seen_ip": "10.0.2.15",
        "vpn_client_version": "5.1.2",
        "recent_auth_failures": 0,
        "assigned_gateway": "gw-eu-west-1",
        "client_os": "Windows 11",
    },
}

# Remediation guide templates
_REMEDIATION_GUIDES: dict[str, str] = {
    "vpn_gateway_degraded": (
        "The VPN gateway serving your region is currently experiencing degraded performance. "
        "Our infrastructure team has been notified. Try connecting to an alternate gateway: "
        "Open VPN client → Settings → Server → Select 'Auto' to be routed to a healthy gateway. "
        "Expected resolution: within 30 minutes."
    ),
    "vpn_client_outdated": (
        "Your VPN client (version {version}) is outdated. "
        "Please update to the latest version (5.1.2): "
        "1. Open Software Center → Search 'VPN Client' → Install update. "
        "2. Restart the client and reconnect. "
        "If the update fails, submit a new ticket tagged 'software'."
    ),
    "vpn_auth_failures": (
        "We detected {failures} recent authentication failures on your VPN account. "
        "Steps to resolve: "
        "1. Ensure your domain password hasn't expired (try logging into the intranet portal). "
        "2. Disconnect any existing VPN sessions. "
        "3. Reconnect using your full email address as the username. "
        "If you're still unable to connect, your account may need a password reset."
    ),
    "vpn_general": (
        "General VPN troubleshooting steps: "
        "1. Restart the VPN client completely (right-click tray icon → Exit, then relaunch). "
        "2. Check your internet connection is working (try opening a website). "
        "3. Ensure you're not on a restricted network (hotel/cafe wifi may block VPN). "
        "4. Try connecting on a mobile hotspot to rule out local network issues. "
        "5. If none of these work, reply to this ticket with your error message."
    ),
}

# Simulated notification log
_NOTIFICATION_LOG: list[dict] = []

# Ticket store (isolated from coordinator — same pattern as other specialists)
_TICKET_STORE: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Tool 1: check_vpn_status
# ---------------------------------------------------------------------------

CHECK_VPN_STATUS_SCHEMA = {
    "name": "check_vpn_status",
    "description": (
        "Query the current health of VPN gateways from the monitoring system. "
        "Returns status (healthy/degraded/down), active connection count, latency, "
        "and last-checked timestamp for each gateway. "
        "Optionally filter to a specific gateway by gateway_id. "
        "Does NOT restart or modify gateways. "
        "Does NOT take any write action. "
        "Does NOT return user-specific connectivity data — use get_user_connectivity_diagnostics for that."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "gateway_id": {
                "type": "string",
                "description": (
                    "Optional specific gateway ID (e.g. 'gw-us-east-1'). "
                    "Omit to get status of all gateways."
                ),
            }
        },
        "required": [],
    },
}


def check_vpn_status(gateway_id: str | None = None) -> dict[str, Any]:
    if gateway_id:
        gw = _VPN_GATEWAY_STORE.get(gateway_id)
        if not gw:
            return _tool_error(
                "GATEWAY_NOT_FOUND",
                f"No gateway with id='{gateway_id}'. Known gateways: {list(_VPN_GATEWAY_STORE.keys())}.",
            )
        return {"gateways": {gateway_id: gw}, "queried_at": _now_iso()}

    return {"gateways": dict(_VPN_GATEWAY_STORE), "queried_at": _now_iso()}


# ---------------------------------------------------------------------------
# Tool 2: get_user_connectivity_diagnostics
# ---------------------------------------------------------------------------

GET_USER_CONNECTIVITY_DIAGNOSTICS_SCHEMA = {
    "name": "get_user_connectivity_diagnostics",
    "description": (
        "Retrieve VPN connectivity diagnostics for a specific user: "
        "last successful VPN authentication timestamp, last seen IP, "
        "VPN client version, recent auth failure count, and assigned gateway. "
        "Does NOT return passwords, credentials, or PII beyond directory-approved fields. "
        "Does NOT show other users' data. "
        "Input: user_id string (e.g. 'U-001')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier (e.g. U-001).",
            }
        },
        "required": ["user_id"],
    },
}


def get_user_connectivity_diagnostics(user_id: str) -> dict[str, Any]:
    data = _USER_CONNECTIVITY_STORE.get(user_id)
    if not data:
        return _tool_error(
            "USER_DIAGNOSTICS_NOT_FOUND",
            f"No connectivity diagnostics for user_id='{user_id}'. "
            "User may not have connected via VPN before.",
        )
    return {"user_id": user_id, **data}


# ---------------------------------------------------------------------------
# Tool 3: push_remediation_guide
# ---------------------------------------------------------------------------

PUSH_REMEDIATION_GUIDE_SCHEMA = {
    "name": "push_remediation_guide",
    "description": (
        "Send a targeted troubleshooting guide to the user via their registered "
        "communication channel (email or Slack). "
        "issue_type must be one of: 'vpn_gateway_degraded', 'vpn_client_outdated', "
        "'vpn_auth_failures', 'vpn_general'. "
        "Does NOT modify network configuration, firewall rules, or VPN gateways. "
        "Does NOT send to unregistered users. "
        "Does NOT resolve the ticket — call close_ticket separately after this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier (e.g. U-001).",
            },
            "issue_type": {
                "type": "string",
                "enum": ["vpn_gateway_degraded", "vpn_client_outdated", "vpn_auth_failures", "vpn_general"],
                "description": "The type of network issue to send a guide for.",
            },
        },
        "required": ["user_id", "issue_type"],
    },
}


def push_remediation_guide(user_id: str, issue_type: str) -> dict[str, Any]:
    guide_template = _REMEDIATION_GUIDES.get(issue_type)
    if not guide_template:
        return _tool_error(
            "UNKNOWN_ISSUE_TYPE",
            f"issue_type='{issue_type}' is not recognised. "
            f"Valid types: {list(_REMEDIATION_GUIDES.keys())}.",
        )

    # Personalise template if user diagnostics available
    diag = _USER_CONNECTIVITY_STORE.get(user_id, {})
    guide = guide_template.format(
        version=diag.get("vpn_client_version", "unknown"),
        failures=diag.get("recent_auth_failures", 0),
    )

    entry = {
        "user_id": user_id,
        "issue_type": issue_type,
        "guide_sent": guide,
        "sent_at": _now_iso(),
        "channel": "email",
    }
    _NOTIFICATION_LOG.append(entry)

    return {
        "sent": True,
        "user_id": user_id,
        "issue_type": issue_type,
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
        "Call this only after push_remediation_guide has returned sent=True, "
        "or after confirming the gateway issue is fully resolved. "
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

NETWORKING_TOOL_SCHEMAS = [
    CHECK_VPN_STATUS_SCHEMA,
    GET_USER_CONNECTIVITY_DIAGNOSTICS_SCHEMA,
    PUSH_REMEDIATION_GUIDE_SCHEMA,
    CLOSE_TICKET_SCHEMA,
]

NETWORKING_TOOL_HANDLERS: dict[str, Any] = {
    "check_vpn_status": check_vpn_status,
    "get_user_connectivity_diagnostics": get_user_connectivity_diagnostics,
    "push_remediation_guide": push_remediation_guide,
    "close_ticket": close_ticket,
}
