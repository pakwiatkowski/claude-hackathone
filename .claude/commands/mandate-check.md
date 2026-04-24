# /mandate-check — Validate a proposed change against the mandate

Before implementing a new feature, auto-resolve category, or tool, check whether
it is within the scope defined in `docs/mandate.md`. Produces a structured verdict.

Arguments: `$ARGUMENTS` — plain-language description of the proposed change.
Example: "auto-resolve VPN password resets for VIP users without identity verification"

## Steps

1. Read `docs/mandate.md` in full.

2. Parse `$ARGUMENTS` as the proposed change. If empty, ask:
   "What change or new automation are you considering?"

3. Evaluate the proposal against each mandate section:

   **Decides alone** — Does the proposal add a new auto-resolve action?
   If yes: is the action reversible? Is it bounded to a single user/ticket?

   **Escalation rules** — Does the proposal bypass any existing escalation trigger?
   List each bypassed rule explicitly.

   **Never touches (hard stops)** — Does the proposal involve any of:
   - Frozen/terminated accounts
   - PII in non-designated fields
   - Financial/payroll systems
   - Prompt-injection-vulnerable inputs

   **Deliberately not automating** — Is the proposal in the exclusion list?

4. Produce a structured verdict:
   ```
   PROPOSAL: <one-line restatement>
   ─────────────────────────────────
   IN SCOPE:       YES / NO / PARTIAL
   BYPASSES RULES: <list or "none">
   HARD STOPS:     <list or "none">
   EXCLUSION LIST: YES / NO

   VERDICT: APPROVED / NEEDS MANDATE UPDATE / BLOCKED

   RATIONALE: <2–3 sentences>

   IF NEEDS UPDATE: Add the following to docs/mandate.md section X: "..."
   ```

5. If verdict is APPROVED, offer to proceed with implementation.
   If NEEDS MANDATE UPDATE, show the exact text to add to `docs/mandate.md` and ask for confirmation before modifying it.
   If BLOCKED, explain which hard stop applies and suggest an alternative approach.
