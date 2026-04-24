# ADR-003: Schema Validation with Specific-Error Retry Rather Than Prompt Engineering Alone

**Status:** Accepted  
**Date:** 2026-04-24  
**Deciders:** Engineering  

---

## Context

The coordinator's routing logic depends on a structured classification result: `priority ∈ {P1,P2,P3,P4}`, `category ∈ {password_reset, network, hardware, software, security_incident, other}`, `confidence ∈ [0.0, 1.0]`, `reasoning` (non-empty string), `auto_resolvable` (boolean).

Every downstream decision — which queue to assign, whether to spawn a specialist, whether to escalate, what to log — is a function of this struct. If the struct is malformed:
- A missing `confidence` field causes the escalation threshold check to silently fail
- An invalid `priority` value (`"P0"`, `"critical"`) breaks queue SLA lookup
- A missing `reasoning` field produces an empty audit log entry
- A non-boolean `auto_resolvable` produces incorrect routing

LLMs produce malformed structured output in three well-known ways:
1. **Wrong enum value** — `"p1"` instead of `"P1"`, `"password reset"` instead of `"password_reset"`, `"yes"` instead of `true`
2. **Missing required field** — the model omits `reasoning` when the issue is obvious to it
3. **Out-of-range value** — `confidence: 1.2`, `confidence: "high"`

The naive approach — rely on the system prompt instruction ("always return valid JSON conforming to this schema") — is insufficient. Prompt instructions constrain the output distribution but do not guarantee conformance. Under adversarial inputs, unusual ticket bodies, or edge cases the prompt didn't anticipate, the model will occasionally produce invalid output. The question is what to do when it does.

---

## Decision

After every `classify_ticket` tool result, validate the output against `TicketClassification` (Pydantic v2 model) before any downstream decision. On `ValidationError`:

1. **Extract the specific error message** from Pydantic (which field, which constraint, what was received)
2. **Feed that exact error back to the model** as the tool result content — not a generic "invalid, retry"
3. **Increment retry counter and append error type** to `error_types[]`
4. **Retry**, up to `MAX_RETRIES = 3`
5. **After MAX_RETRIES**: escalate with `escalation_reason = "schema_validation_exhausted"` and include the full retry log in the audit record

The retry feedback message takes the form:
```
"classify_ticket result failed schema validation (attempt 2/3):
 1 validation error for TicketClassification
 confidence
   Input should be less than or equal to 1 [type=less_than_equal, input_value=1.2, input_type=float]
 Correct and retry."
```

This is the specific Pydantic error string — field name, constraint, actual value received. The model can address it directly.

**What the loop does NOT do:**
- It does not silently coerce invalid values (e.g. clamp `confidence: 1.2` to `1.0`)
- It does not retry with a generic "your output was invalid" message
- It does not retry the same prompt without any feedback (hoping for a different draw)
- It does not continue past `MAX_RETRIES` with a potentially invalid classification

**Retry log in the audit record.** Every `update_ticket` call includes `retry_count` and `error_types[]`. A ticket that required two retries produces an audit entry like:
```json
{
  "retry_count": 2,
  "error_types": [
    "confidence: Input should be less than or equal to 1 [input_value=1.2]",
    "priority: Input should be 'P1', 'P2', 'P3' or 'P4' [input_value='P0']"
  ]
}
```

This serves two purposes: (1) detecting systemic model drift — if retry rates rise across tickets, the prompt or model needs attention; (2) providing a defensible audit record — every routing decision is traceable to a valid classification or a documented escalation.

---

## Consequences

**Positive:**
- Schema violations are caught before they corrupt downstream routing. A ticket cannot be silently mis-routed because `priority` was `"critical"` instead of `"P1"`.
- Feeding the specific error enables effective correction. The model knows exactly which constraint it violated and what it provided. Empirically, specific-error feedback produces valid output on the first retry in the large majority of cases that fail the initial attempt.
- Retry metadata in the audit log makes quality degradation visible. If `avg(retry_count)` rises from 0.1 to 0.8 over a week, something changed — ticket distribution, model behavior, or prompt fitness.
- Graceful degradation: retry exhaustion escalates to tier2 with a full retry log rather than routing silently wrong. The human reviewer can see exactly what the model attempted and why it failed.
- `MAX_RETRIES = 3` is a config constant (`src/config.py`), not a magic number embedded in the loop. Adjusting it requires changing one value.

**Negative:**
- Up to 3× classification latency in the worst case (three API round trips). For a P4 ticket this is acceptable. For P1 the retry loop is moot — P1 always escalates regardless of classification confidence.
- The retry loop adds code complexity to the coordinator event loop. It must be tested explicitly (the `eval-scenario` skill generates low-confidence cases that exercise it).
- The loop validates only the `classify_ticket` result. Other tool results (lookup_user, route_ticket) are not schema-validated. Extending validation to all tools is a future consideration if those tools develop their own reliability issues.

---

## Alternatives Considered

### Rely on system prompt instructions alone

Instruct the model: "Return a JSON object with exactly these fields and these valid values."

**Rejected because:**
- Works the majority of the time, fails silently when it doesn't. Silent failure is strictly worse than a retry: the downstream routing is wrong, there is no log entry of the failure, and the ticket may be mis-prioritised or mis-routed without any signal that something went wrong.
- The failure rate is low but non-zero and non-uniform. Edge cases — unusual ticket wording, non-English content, adversarial injection — are exactly the cases where model output quality is most likely to deviate from prompt expectations.

### Silent coercion (normalize invalid values)

If `confidence = 1.2`, clamp to `1.0`. If `priority = "p1"`, upcase to `"P1"`.

**Rejected because:**
- Masks the failure. A coordinator that returns `confidence: 1.2` has misunderstood something — coercing it hides the signal.
- Coercion rules are incomplete: what is the correct coercion for `priority: "critical"`? `"P1"`? What about `priority: "urgent"`? The mapping is ambiguous and domain-specific.
- Adds a parallel normalisation layer that must be maintained alongside the schema. The schema and the coercion rules will eventually diverge.
- The audit log records the coerced value, not what the model actually produced. The record is misleading.

### Structured outputs / `response_format` enforcement

Use the API's built-in structured output mode to guarantee the schema.

**Rejected because:**
- Structured output guarantees syntactic conformance (valid JSON matching the schema) but does not guarantee semantic correctness — `confidence: 0.0` and `auto_resolvable: false` for every ticket would be syntactically valid but useless.
- The current implementation uses tool-use flow (`classify_ticket` as a tool), not a separate response-format call. Switching to a structured-output call would require a separate API call outside the tool loop, adding latency and complexity.
- The retry loop's value is not just schema enforcement — it is the feedback loop. Telling the model exactly what it got wrong is a capability that structured output mode does not provide.
- Revisit if the SDK adds structured output support within tool-use flows.

### Single attempt, escalate on any failure

If the first classification attempt produces invalid output, immediately escalate.

**Rejected because:**
- The model produces invalid output occasionally due to statistical variance, not systemic failure. A single retry with specific error feedback recovers the vast majority of transient failures.
- Escalating on first failure means any edge-case ticket body would overwhelm tier2 with escalations that a single retry would have resolved. The escalation queue has a cost (human attention), and exhausting it on recoverable failures degrades its value for genuine escalations.

---

## References

- `src/agents/coordinator.py` — retry loop implementation (search for `ValidationError`)
- `src/models/schemas.py:TicketClassification` — the schema being validated
- `src/config.py:MAX_RETRIES` — configurable retry ceiling
- `.claude/commands/eval-scenario.md` — generates low-confidence test cases that exercise the retry loop
- ADR-001 — explains why the retry loop lives in the coordinator, not the specialist
