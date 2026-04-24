# ADR-001: IT Helpdesk Triage Agent Architecture

**Status:** Accepted  
**Date:** 2026-04-24  
**Deciders:** Engineering, IT Operations, Legal

---

## Context

The IT helpdesk receives ~300 tickets/day across Jira Service Management, Slack `#it-help`, and a web portal. Triage is done manually by a single tier1 analyst. Average time-to-first-response is 3.5 hours; password resets alone account for 38% of volume and are fully mechanical. We need an agent that classifies every ticket, assigns a queue, and auto-resolves the safe subset without human intervention.

---

## Decision

Build a **Coordinator + Specialist Subagent** system on the Claude Agent SDK (Python). The coordinator owns all classification and routing logic. Auto-resolvable tickets are delegated to isolated Task subagents.

---

## Architecture

```
Incoming ticket (Jira / Slack / portal)
         │
         ▼
┌────────────────────────────────────────────────────┐
│                  Coordinator Agent                  │
│                                                     │
│  1. classify_ticket ──► {priority, category,        │
│                          confidence, auto_resolvable}│
│                                                     │
│  2. lookup_user ──────► {account_status, vip_flag,  │
│                          department}                │
│                                                     │
│  3. Validate schema ──► retry loop (max 3)          │
│     on failure: feed specific error back to Claude  │
│     log: retry_count, error_types[]                 │
│                                                     │
│  4a. auto_resolvable=True                           │
│      confidence ≥ 0.70                             │
│      priority ≠ P1                                  │
│      vip=False OR priority=P3/P4  ──────────────────┼──► spawn Task subagent
│                                                     │
│  4b. else ──► route_ticket (assign queue + SLA)     │
│                                                     │
│  5. update_ticket ────► reasoning chain JSON        │
│     (all paths, always)                             │
└────────────────────────────────────────────────────┘
                    │ (auto-resolvable path only)
                    ▼
┌────────────────────────────────────────────────────┐
│         PasswordResetSpecialist (Task subagent)     │
│                                                     │
│  Receives: {ticket_id, user_id, issue_summary}      │
│  Does NOT inherit coordinator context               │
│                                                     │
│  1. lookup_account ──► status, failed_attempts      │
│  2. verify_identity ─► challenge/response           │
│  3. reset_password ──► temp credentials + delivery  │
│  4. close_ticket ────► resolved + summary           │
│                                                     │
│  On any isError=true response: return escalation    │
│  signal, coordinator re-routes to tier2             │
└────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### Coordinator Agent

- Single entry point for all incoming tickets
- Owns P1–P4 classification and queue routing
- Owns the validation-retry loop (up to `MAX_RETRIES=3`)
- Assembles the complete reasoning chain for every ticket
- Decides whether to spawn a specialist or route to a human queue
- Never performs writes to external systems directly — delegates to specialists

### PasswordResetSpecialist (Task Subagent)

- Activated only for `category=password_reset`, `auto_resolvable=True`, confidence ≥ 0.70
- Receives a minimal, explicit context payload — it does **not** inherit the coordinator's conversation history, system prompt, or any other ticket context
- Has its own isolated tool set (4 tools, see below)
- If any tool returns `isError=true`, it signals escalation rather than retrying autonomously

### Context Isolation

The coordinator passes exactly this to the specialist Task prompt:

```json
{
  "ticket_id": "T-12345",
  "user_id": "U-98765",
  "issue_summary": "User locked out after 5 failed login attempts",
  "identity_pre_verified": false
}
```

Nothing else. The specialist cannot see the coordinator's system prompt, prior classification reasoning, user's full ticket history, or any other coordinator state.

---

## Agent Loop and `stop_reason` Handling

Both agents use the same loop structure:

```
open stream
send user.message (ticket or task payload)

loop:
  event = next(stream)

  agent.custom_tool_use
    → execute tool locally
    → send user.custom_tool_result

  session.status_idle where stop_reason.type = "requires_action"
    → for each pending event:
        if custom_tool_use → execute + respond
        if tool_use (built-in, needs permission) → run PreToolUse hook
            allowed  → send user.tool_confirmation {result: "allow"}
            denied   → send user.tool_confirmation {result: "deny", deny_message}

  session.status_idle where stop_reason.type = "end_turn"
    → break, collect result

  session.status_terminated
    → log error, surface to caller as escalation
```

---

## Tool Sets

### Coordinator (4 tools)

| Tool | Purpose | Does NOT |
|---|---|---|
| `classify_ticket` | Classify priority + category + confidence | Infer from ticket number; handle attachments |
| `lookup_user` | Fetch account context from directory | Access payroll or financial data |
| `route_ticket` | Assign queue + set SLA | Close or resolve tickets |
| `update_ticket` | Write reasoning chain + retry metadata | Make routing decisions |

### PasswordResetSpecialist (4 tools)

| Tool | Purpose | Does NOT |
|---|---|---|
| `lookup_account` | Get account status and lock info | Return passwords or secrets |
| `verify_identity` | Challenge/response identity check | Bypass on partial match; log security answers |
| `reset_password` | Generate and deliver temp credentials | Run without prior identity verification |
| `close_ticket` | Mark resolved with summary | Escalate or re-route |

Tool count is deliberately capped at 4–5 per agent. Tool-selection reliability degrades beyond that range.

---

## Validation-Retry Loop

```
attempt = 0
while attempt < MAX_RETRIES:
    call classify_ticket(...)
    result = parse JSON from tool response
    try:
        TicketClassification.model_validate(result)
        break  # valid
    except ValidationError as e:
        attempt += 1
        error_types.append(str(e))
        send back to Claude: f"Classification failed schema validation: {e}. Retry."

if attempt == MAX_RETRIES:
    escalate(reason="schema_validation_exhausted", retry_log=error_types)
```

The specific `ValidationError` message is always fed back to Claude — not a generic "try again". This gives the model the exact constraint it violated so it can correct it.

---

## Escalation Rules

Escalation is explicit. No vague "when the agent isn't sure."

| Rule | Trigger | Action |
|---|---|---|
| P1 | `priority=P1` | Route to tier2, require human acknowledgement |
| Low confidence | `confidence < 0.70` | Route to tier2 with confidence score |
| Security incident | `category=security_incident` | Route to security queue, notify Security team |
| Sensitive mention | payroll/finance/termination in ticket or user metadata | Route to tier2 with flag |
| Retry exhaustion | `retry_count = MAX_RETRIES` | Route to tier2 with full retry log |
| VIP + high priority | `vip=True AND priority IN [P1, P2]` | Route to tier2, flag as VIP |

---

## Hard Stops (`PreToolUse` Hook)

Applied before any tool confirmation is sent. Cannot be overridden by the agent.

| Pattern | Block condition |
|---|---|
| `reset_password` | Account `status=frozen` or `status=terminated` |
| Any tool | Input field (outside PII-designated fields) matches `\d{3}-\d{2}-\d{4}` (SSN) |
| Any tool name | Matches `payroll_*` or `finance_*` |
| `route_ticket` | Ticket body matches known prompt-injection patterns |

---

## Alternatives Considered

**Single-agent (no subagents):** Simpler, but the coordinator's context window grows with every specialist action. Context pollution degrades classification accuracy over high-volume sessions.

**Three or more specialist subagents up front:** Premature. Only password reset meets the auto-resolve volume threshold today. Network and hardware specialists can be added when the eval harness confirms their accuracy meets the 95% precision bar.

**TypeScript SDK:** Python chosen for faster iteration and richer data-validation ecosystem (Pydantic). TypeScript variant is a viable future migration path.

---

## Consequences

- Coordinator has no direct write access to external systems — all writes flow through tools. This makes it straightforward to audit or mock for testing.
- Adding a new specialist requires: (1) a new tool file, (2) a new specialist agent function, (3) an entry in the coordinator routing logic, (4) eval coverage in The Scorecard. Nothing else changes.
- The hard-stop hook runs synchronously in the event loop — adding patterns is a one-line addition to `pre_tool_use.py`.
