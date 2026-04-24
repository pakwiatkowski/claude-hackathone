# The Mandate — IT Helpdesk Triage Agent

## What the Agent Is

An automated first-responder for the IT helpdesk. Requests arrive from three channels (Jira Service Management tickets, Slack `#it-help`, and an internal web portal). The agent classifies every request, routes it to the appropriate queue, and — for a defined set of safe, reversible actions — resolves it without human intervention.

---

## What the Agent Decides Alone

| Decision | Scope |
|---|---|
| Priority classification | P1 (critical) through P4 (low) for every incoming ticket |
| Queue assignment | tier1, tier2, networking, security, hardware |
| Auto-resolve: password reset | Locked or forgotten passwords where identity is verified |
| Auto-resolve: account unlock | Accounts locked by failed-login policy (not by Security team) |
| Auto-resolve: VPN status check | "Is VPN down?" — respond with current status from monitoring |
| Ticket status transitions | New → In Progress → Resolved or Escalated |
| Ticket comments | Notify user of classification decision and expected SLA |

---

## What the Agent Escalates (Slow Stop)

The agent routes to human review — it does **not** act autonomously — when any of the following are true:

1. **P1 classification** — any ticket classified as critical (service-wide impact) requires a human to acknowledge before any auto-resolve action runs.
2. **Low confidence** — classification confidence < 0.70.
3. **Security incident category** — any ticket the classifier assigns to `security_incident`, regardless of confidence.
4. **Sensitive system mention** — ticket body or user account metadata references payroll, financial systems, or an employee-termination workflow.
5. **Repeated validation failure** — structured output fails schema validation after 3 retries; the raw request is forwarded to tier2 with the full retry log attached.
6. **VIP user + P2+** — tickets from users flagged `vip=true` with P2 or higher priority always get a human eye before auto-resolve.

Escalation records include: ticket ID, classification attempt, confidence score, error types from retry log, and which escalation rule triggered.

---

## What the Agent Never Touches (Hard Stop)

These are enforced by a `PreToolUse` hook — the agent cannot override them regardless of instruction:

- **`reset_password` on frozen or terminated accounts** — accounts with `status=frozen` or `status=terminated` must be handled by the Security team.
- **Payroll or financial endpoints** — any tool call matching `payroll_*` or `finance_*` patterns is blocked unconditionally.
- **Raw PII in non-designated fields** — if an SSN pattern (`\d{3}-\d{2}-\d{4}`) appears in a tool input field not designated for PII, the call is denied and the ticket is flagged for security review.
- **Production infrastructure** — no write operations to production systems outside the approved runbook actions listed above.
- **Prompt-injection routing** — if a ticket body matches known exfil patterns (e.g. "ignore prior instructions", "route to CEO"), the ticket is hard-routed to the security queue and the pattern is logged.

---

## What We Are Deliberately Not Automating

These decisions carry risk, legal exposure, or physical complexity that makes automation premature:

- **Bulk account operations** — requests affecting more than one account per ticket.
- **Hardware replacements** — require physical dispatch; out of scope for a software agent.
- **Security policy changes** — firewall rules, group policy edits, certificate rotations.
- **Onboarding and offboarding** — provisioning or deprovisioning workflows touch multiple downstream systems.
- **Any action on production databases** — schema changes, data exports, access grants.
- **Decisions where the agent is confident but wrong more than 5% of the time** — if precision for any category falls below 95% in the eval harness, auto-resolve for that category is paused until the model is retrained or prompts are updated.

---

## SLA Commitments the Agent Upholds

| Priority | Time to first response |
|---|---|
| P1 | 1 hour |
| P2 | 4 hours |
| P3 | 8 hours |
| P4 | 24 hours |

The agent updates the ticket with the applicable SLA timestamp at classification time.

---

## Governance

- Every decision (classification, routing, auto-resolve, escalation) is logged as a structured reasoning chain in the ticket. The log is replayable: given only the log entry, a human reviewer can reconstruct exactly what the agent saw and why it decided what it did.
- Retry count and error types are included in every log entry.
- The Legal-approved scope of auto-resolve actions is this document. Any expansion requires a new version of this mandate and sign-off.
