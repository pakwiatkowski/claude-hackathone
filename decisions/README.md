# Architecture Decision Records

Decisions that shaped the system and would not be obvious from reading the code alone.

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-coordinator-specialist-split.md) | Coordinator + Specialist Subagent Split | Accepted |
| [ADR-002](ADR-002-synchronous-hard-stop-hook.md) | Synchronous Hard-Stop Hook as a Separate Gate from LLM-Driven Escalation | Accepted |
| [ADR-003](ADR-003-validation-retry-loop.md) | Schema Validation with Specific-Error Retry Rather Than Prompt Engineering Alone | Accepted |

## What each ADR covers

**ADR-001** answers: *Why split the coordinator from the specialist at all?* Documents the context contamination problem at volume, the tool-set reliability argument, and the permission separation rationale. Rejects single-agent, three-tier, and event-driven alternatives.

**ADR-002** answers: *Why is the hard-stop hook a Python gate rather than a system prompt rule?* Documents why LLM-based guardrails are insufficient for categorical prohibitions (prompt injection, distribution shift, no unit testability), the two-layer model (hard stop vs escalation), and why a rule-based Python function is strictly better than a safety model for known-bad patterns.

**ADR-003** answers: *Why validate-and-retry rather than trust the LLM to produce valid JSON?* Documents the three common structured-output failure modes, why specific-error feedback outperforms generic retry, why silent coercion is dangerous, and why retry metadata in the audit log is operationally necessary.
