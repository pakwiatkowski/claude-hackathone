# ADR-001: Coordinator + Specialist Subagent Split

**Status:** Accepted  
**Date:** 2026-04-24  
**Deciders:** Engineering, IT Operations  

---

## Context

The system must classify incoming IT tickets (P1–P4), assign them to queues, and for a defined safe subset, resolve them end-to-end without human intervention. Two architectural shapes are viable:

1. **Single agent** — one context window, all tools, handles classification and execution
2. **Split agents** — coordinator owns intake and routing; specialists own execution in isolated contexts

The pressure toward the split comes from three directions:

**Context contamination.** An agent that classifies ticket #1, routes it, then starts on ticket #2 carries forward the tool results, user data, and reasoning from ticket #1 into ticket #2's classification. In a production system processing ~300 tickets/day in a single session, context grows monotonically. Classification accuracy measurably degrades as irrelevant prior-ticket content competes for attention in the prompt.

**Tool set pollution.** A single agent handling both routing and execution must carry all tools from both domains — in our case, eight tools across two concerns (classify, lookup_user, route_ticket, update_ticket, lookup_account, verify_identity, reset_password, close_ticket). Tool-selection reliability is known to degrade beyond 4–5 tools per agent. A single agent with eight tools increases the probability of the model reaching for the wrong tool under ambiguous inputs.

**Audit and permission separation.** The routing decision (what priority, which queue, which team) and the execution (what actions were taken on which account) are distinct concerns with distinct audiences. Legal reviews routing decisions; Security reviews execution. Mixing them into one agent and one log entry makes it harder to answer "why was this routed to security?" vs "what exactly did the agent do to this account?" The permission boundary also matters: the coordinator needs no write access to external systems; only the specialist does. Giving the coordinator write tools it never uses unnecessarily expands the blast radius of a coordinator failure.

---

## Decision

Implement a **Coordinator + Specialist Subagent** architecture using the Claude Agent SDK.

**Coordinator responsibilities:**
- Receives every incoming ticket regardless of category
- Classifies priority, category, and confidence
- Enriches with user/account context
- Decides: auto-resolve (spawn specialist) or route to human queue
- Owns the validation-retry loop for structured output
- Writes the full reasoning chain to the audit log

**Specialist responsibilities:**
- Activated only for a specific category (currently: `password_reset`)
- Receives an explicit, minimal context payload — it does NOT inherit the coordinator's conversation history, system prompt, or any prior classification reasoning
- Has a focused tool set (4 tools, each scoped to its domain)
- If any tool returns `isError: true`, it signals escalation to the coordinator rather than retrying autonomously

**Context isolation contract.** The coordinator passes exactly:
```json
{
  "ticket_id": "T-12345",
  "user_id": "U-98765",
  "issue_summary": "User locked out after 5 failed login attempts"
}
```
Nothing else. The specialist cannot infer the coordinator's confidence score, the retry history, the user's VIP status, or anything else the coordinator knows. If it needs more context, it must acquire it through its own tools.

This is a deliberate constraint, not an oversight. It ensures the specialist prompt stays minimal, the specialist's tool calls are scoped to its domain, and the specialist cannot accidentally act on coordinator-context data it should not have.

---

## Consequences

**Positive:**
- Coordinator context remains bounded across a high-volume session — each classification uses only the current ticket, not accumulated prior-ticket noise
- Coordinator has no write tools — a prompt-injection attack on the coordinator cannot trigger password resets or account changes
- Each agent has 4 tools, within the reliability sweet spot
- Routing reasoning and execution reasoning are in separate log entries, making audit-trail queries straightforward
- Adding a new specialist (network, hardware) is additive: new tool file, new agent function, one routing branch in the coordinator — nothing else changes

**Negative:**
- Additional operational complexity: two agent loops, context marshalling, error propagation from specialist back to coordinator
- The coordinator cannot observe the specialist's intermediate tool calls; it receives only the final result dict. Debugging specialist failures requires reading specialist logs separately.
- Latency is additive: coordinator finishes its loop, then the specialist loop begins. For P3/P4 auto-resolve cases this is acceptable; for P1 it is moot (P1 always escalates to a human).

---

## Alternatives Considered

### Single agent with all tools

A single agent with the full 8-tool set handles both classification and execution.

**Rejected because:**
- Context contamination across tickets in a multi-ticket session is not hypothetical — it is an expected failure mode at volume. A single session processing 10 password-reset tickets will accumulate 10 × (lookup_user + verify_identity + reset_password + close_ticket) results in context before ticket #11 is classified.
- Eight tools per agent exceeds the 4–5 tool reliability band. In adversarial testing (The Attack), ambiguous inputs are more likely to trigger the wrong tool when the choice set is larger.
- There is no natural permission boundary. A single agent that has `reset_password` in its tool set can — through prompt injection or hallucination — attempt to call it during the classification phase.

### Three-tier architecture (intake → coordinator → specialist → executor)

A separate executor agent handles the actual writes; the specialist only plans.

**Rejected because:**
- Over-engineered for current scope. The specialist's write operations (reset_password, close_ticket) are two deterministic tool calls, not a planning problem. A third agent tier adds an additional context handoff, an additional error-propagation path, and measurable latency for no reliability gain at this scale.
- Revisit if a specialist's execution logic becomes complex enough to require its own planning loop.

### Event-driven queue between coordinator and specialists

Coordinator publishes to a queue; specialists consume asynchronously.

**Rejected because:**
- Requires infrastructure the current stack does not have (message broker, persistent queue, consumer workers).
- Introduces partial-failure modes (message delivered but specialist crashed) that require dead-letter handling.
- Tickets are currently processed synchronously — the submitter expects a near-real-time acknowledgement. Async processing would require a notification callback mechanism.
- Reconsider if volume grows to the point where synchronous processing creates a backlog.

---

## References

- `src/agents/coordinator.py` — coordinator implementation
- `src/agents/specialists/password_reset.py` — specialist implementation
- `docs/architecture-adr.md` — ASCII flow diagram
- ADR-002 — hard-stop hook placement (consequence of coordinator having no write tools)
- ADR-003 — validation-retry loop (lives in coordinator, not specialist)
