# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Level 1 — Project Root

### Project Overview

This system is an IT helpdesk triage agent that classifies every incoming support ticket (P1–P4), assigns it to one of five queues (tier1, tier2, networking, security, hardware), and resolves a defined subset end-to-end without human intervention. The **coordinator_agent** handles intake, classification, user enrichment, and the routing decision; for tickets that qualify for auto-resolution it spawns the **password_reset_specialist**, which owns the full verify-and-reset loop. The **triage_specialist** handles ambiguous multi-category tickets that need deeper analysis before routing. The **escalation_specialist** manages P1 incidents, assembling the incident record and notifying stakeholders. Anything outside the known-good auto-resolve templates, below the confidence threshold, or flagged by the PreToolUse hook is routed to a human queue — the agent never silently drops a ticket.

Auth: set `ANTHROPIC_API_KEY` in environment.

SDK docs:
- Overview: docs.claude.com/en/api/agent-sdk/overview
- Python: docs.claude.com/en/api/agent-sdk/python
- TypeScript: docs.claude.com/en/api/agent-sdk/typescript
- Custom tools: docs.claude.com/en/api/agent-sdk/custom-tools
- Permissions/hooks: docs.claude.com/en/api/agent-sdk/permissions

---

### Architecture Conventions

- Agent files use snake_case and end in `_agent.py` or `_specialist.py` — e.g. `coordinator_agent.py`, `password_reset_specialist.py`.
- Tool functions use verb_noun naming — e.g. `reset_password`, `lookup_cmdb_asset`, `route_ticket`, `verify_identity`.
- Each specialist carries at most 5 tools; if a specialist needs a 6th tool, add an entry to `decisions/` explaining why before adding it.
- Every tool that fails must return `{ "isError": true, "code": "SCREAMING_SNAKE_CASE", "guidance": "one sentence telling the agent what to try next" }` — no plain strings, no exceptions propagating to the agent loop.
- Task subagents receive only the fields they need — never pass the full coordinator message history, confidence score, retry metadata, or VIP flag unless the specialist's prompt explicitly requires it.
- Every agent event loop must handle `stop_reason` values `tool_use`, `end_turn`, `max_tokens`, and `error` in explicit branches — no silent fallthrough to a default that swallows unknown stop reasons.
- The coordinator has zero write tools — all external writes belong to specialists.
- The PreToolUse hook in `src/hooks/pre_tool_use.py` runs before every tool confirmation for both the coordinator and all specialists; it cannot be bypassed.

---

### File Structure

```
src/
  agents/
    coordinator_agent.py        # intake, classify, enrich, route
    triage_specialist.py        # deep analysis for ambiguous tickets
    escalation_specialist.py    # P1 incident assembly + notification
    specialists/
      password_reset_specialist.py
  tools/
    coordinator_tools.py        # classify_ticket, lookup_user, route_ticket, update_ticket
    password_reset_tools.py     # lookup_account, verify_identity, reset_password, close_ticket
    triage_tools.py
    escalation_tools.py
  hooks/
    pre_tool_use.py             # synchronous hard-stop gate
  models/
    schemas.py                  # Pydantic v2 models (TicketClassification, RouteDecision, ToolError)
  config.py                     # MODEL, MAX_RETRIES, CONFIDENCE_THRESHOLD, QUEUES, SLA_HOURS
  main.py                       # CLI entry point

docs/
  mandate.md                    # governance: what agent decides, escalates, never touches
  architecture-adr.md           # top-level architecture diagram

decisions/
  ADR-NNN-title.md              # one file per architectural decision with > 1 option

tests/
  test_tools/                   # unit tests per tool module
  test_hooks/
  test_agents/                  # integration tests per agent loop

outputs/
  audit/                        # update_ticket JSON records (gitignored in prod)
```

Prompts live as docstrings on the agent function or as inline strings in the agent file — not in separate `.txt` files, so they stay co-located with the loop that uses them.

---

### Coding Conventions

- Python 3.11+ throughout; every function signature carries full type hints including return type.
- Every tool function has a docstring: the first line is the exact description string the agent sees in the tool schema; subsequent lines are implementation notes not exposed to the model.
- Never use bare `except` — catch `anthropic.APIError`, `pydantic.ValidationError`, `KeyError`, etc. specifically and return a structured `ToolError`-shaped dict.
- Every write operation appends to the audit trail before the write executes — if the audit write fails, abort the tool call and return an error.
- `ANTHROPIC_API_KEY` is the only secret; load it via `python-dotenv` from `.env`; no other credentials appear in code or config files.
- Pydantic v2 models validate all structured tool outputs before they influence any downstream decision — never trust raw dict shapes from the model.
- `MAX_RETRIES`, `CONFIDENCE_THRESHOLD`, `SLA_HOURS`, and queue names are constants in `src/config.py` — never hardcode them in agent or tool files.

---

### What Claude Code Should Always Do

- Check `src/tools/` for an existing tool that covers the need before creating a new one.
- Write the unit test for a new tool in `tests/test_tools/` in the same task as the tool implementation, not afterwards.
- Add an entry to `decisions/` for any architectural choice where more than one option was considered — use the existing ADR format.
- Run `python -m pytest tests/` after any change to a tool schema or Pydantic model before considering the task done.
- When adding a hard-stop pattern to `pre_tool_use.py`, also add the corresponding entry to `docs/mandate.md` under "What the Agent Never Touches".
- Validate that every new specialist receives only the minimum required context fields — check against the context isolation contract in `decisions/ADR-001-coordinator-specialist-split.md`.

---

### What Claude Code Should Never Do

- Add any tool that writes to an external system to `coordinator_agent.py` — writes belong in specialists only.
- Skip or conditionally bypass `check_pre_tool_use()` for any tool that modifies account state, ticket state, or routes to an external queue.
- Create a new specialist agent when a new tool on an existing specialist would cover the use case — specialists multiply operational complexity.
- Commit `.env` files, API keys, real employee records, or real ticket bodies — the data stores in `src/tools/` are stubs with synthetic data only.
- Use `model_validate` with `strict=False` or silent coercion to paper over a schema violation — feed the exact `ValidationError` text back to the model and retry.
- Inline multi-paragraph prompt text in the middle of control flow — keep system prompts as named string constants at the top of the agent file.

---

### Escalation Thresholds (Reference)

These rules are enforced by coordinator reasoning and must be consistent across all sessions.

- **P1**: service fully down AND more than 50 users affected, OR the affected user is C-suite — always escalates to `escalation_specialist`, never auto-resolved.
- **P2**: service degraded for a group OR a single user is fully blocked from their primary work tool — routes to tier2; auto-resolve only if the issue matches a known-good template with confidence > 0.95.
- **P3**: partial functionality lost but a documented workaround exists — routes to tier1 or the relevant specialist queue; auto-resolve eligible.
- **P4**: cosmetic issue, informational request, or low-urgency improvement — routes to tier1; auto-resolve eligible.
- **Auto-resolve eligibility**: category must be `password_reset` or `account_unlock`, confidence must exceed 0.95, priority must not be P1, account status must not be `frozen` or `terminated`, and the ticket must not have triggered any PreToolUse denial in the current session.
- **Confidence fallback**: any classification below `CONFIDENCE_THRESHOLD` (0.70) escalates with `reason_code = low_confidence` regardless of category or priority.

---

## Level 2 — /agents Directory

### New Specialist Template

Every specialist follows this structure:

```python
SYSTEM_PROMPT = """
You are the <Domain> Specialist for the IT helpdesk.
Your task for each job:
1. <first tool call>
2. <second tool call — only after step 1 succeeds>
...
If any tool returns isError=true, return an escalation signal immediately.
Do not retry a failed write tool. Do not infer account state — always call lookup first.
"""

def run_<name>_specialist(
    ticket_id: str,
    user_id: str,
    issue_summary: str,
) -> dict:
    """Run the <name> specialist loop. Returns result dict or escalation signal."""
```

- The function signature accepts only the fields listed in the context isolation contract — no `**kwargs`, no passing the coordinator result dict directly.
- Tool list is defined as a module-level constant `SPECIALIST_TOOLS: list[dict]` in the same file — the agent loop passes `tools=SPECIALIST_TOOLS`.

### Required Fields in Every Task Call

When spawning a specialist via the messages API (or Agent SDK Task), always pass:

- `ticket_id` — for audit trail correlation.
- `user_id` — the subject of the action, not the submitter if they differ.
- `issue_summary` — one sentence, no raw ticket body, no prior classification reasoning.

Never pass: `confidence`, `retry_count`, `vip_flag`, `coordinator_reasoning`, or any field not listed in the specialist's function signature.

### stop_reason Handling

Every agent event loop must implement all four branches explicitly:

```python
match response.stop_reason:
    case "tool_use":
        # extract tool use block, run check_pre_tool_use, execute or deny
    case "end_turn":
        # collect final text, build result dict, return
    case "max_tokens":
        # log truncation warning, return escalation signal with code=MAX_TOKENS_EXCEEDED
    case _:
        # log unknown stop_reason, return escalation signal with code=UNKNOWN_STOP_REASON
```

- `max_tokens` must never silently continue — truncated output may represent a partial write instruction; always escalate.
- Unknown stop reasons are treated as errors, not as `end_turn` equivalents.

### Thinking Block Capture

If extended thinking is enabled, capture the thinking block before the text block:

```python
thinking_text = next(
    (b.thinking for b in response.content if b.type == "thinking"), ""
)
```

- Append `thinking_text` to the `reasoning_chain` field passed to `update_ticket`.
- Never surface thinking content to the end user or include it in ticket comments.
- Thinking blocks are stored in the audit trail only — not in the ticket itself.

### Validation-Retry Loop (Coordinator Only)

- After every `classify_ticket` tool result, validate against `TicketClassification` using `TicketClassification.model_validate(raw)`.
- On `ValidationError`, send the exact Pydantic error string back as the tool result content — include attempt number and max retries.
- Increment `retry_count` and append the error type to `error_types: list[str]` on each failure.
- After `MAX_RETRIES` failures, call `update_ticket` with `escalation_reason = "schema_validation_exhausted"` and return — do not route.
- The retry loop lives only in the coordinator; specialists do not retry classification.

---

## Level 3 — /tools Directory

### Tool Function Signature Pattern

```python
def verb_noun(param_one: str, param_two: str) -> dict:
    """First line: exactly what this tool does — this becomes the agent-facing description.

    Implementation notes (not shown to agent):
    - Note about stub vs real integration.
    - Note about side effects or ordering constraints.
    - Note about what this tool does NOT do.
    """
```

- Return type is always `dict` — never a Pydantic model instance, never a plain string.
- All parameters are keyword-only in the tool schema even if positional in Python.
- The tool description (first docstring line) must state at least one thing the tool does NOT do — e.g. "Does not close the ticket; only assigns the queue."

### Tool Docstring as Schema Description

The build step extracts the first line of each tool's docstring to populate `"description"` in the tool schema dict. Keep that line under 120 characters and use active voice. Do not put parameter descriptions in the first line — those go in the schema's `"properties"` `"description"` fields.

### Dry-Run / Preview Pattern

Any tool with external writes must support `dry_run: bool = False`:

```python
def reset_password(user_id: str, delivery_method: str, dry_run: bool = False) -> dict:
    if dry_run:
        return {"dry_run": True, "would_send_to": _get_delivery_address(user_id, delivery_method)}
    # ... actual write
```

- The agent system prompt for the specialist instructs it to call with `dry_run=True` first when operating in preview mode.
- Preview mode is activated by passing `preview=True` to `run_<name>_specialist()`.
- Dry-run results are logged to the audit trail with `dry_run=true` so the record is complete even if the real write never executes.

### Registering a New Tool

1. Implement the function in the relevant `src/tools/<module>_tools.py`.
2. Add the JSON schema dict to the module-level `<SPECIALIST>_TOOL_SCHEMAS: list[dict]` constant in the same file.
3. Add the handler entry to `<SPECIALIST>_TOOL_HANDLERS: dict[str, Callable]` in the same file.
4. Import and pass `<SPECIALIST>_TOOL_SCHEMAS` and `<SPECIALIST>_TOOL_HANDLERS` in the specialist agent file — no other registration step.
5. Write the unit test in `tests/test_tools/test_<module>_tools.py` before considering the tool complete.
6. Run `python -m pytest tests/test_tools/` to confirm the schema is importable and the handler is callable.

### Structured Error Codes

All errors returned from tool functions must use one of these codes in the `"code"` field. Add a new code to this list and to `src/models/schemas.py` before using it.

| Code | When to use |
|---|---|
| `ACCOUNT_FROZEN` | `reset_password` or `lookup_account` called on a frozen/terminated account |
| `ACCOUNT_NOT_FOUND` | `user_id` does not exist in the user or account store |
| `IDENTITY_NOT_VERIFIED` | `reset_password` called before a successful `verify_identity` in the same session |
| `ACCOUNT_NOT_ELIGIBLE` | Account state (not frozen, but otherwise ineligible) prevents the requested action |
| `QUEUE_NOT_FOUND` | `route_ticket` called with a queue name not in `config.QUEUES` |
| `TICKET_NOT_FOUND` | `update_ticket` or `close_ticket` called with an unknown `ticket_id` |
| `TICKET_ALREADY_CLOSED` | Write tool called on a ticket already in `Resolved` or `Closed` state |
| `IDENTITY_MISMATCH` | `verify_identity` called with credentials that do not match the record |
| `DELIVERY_METHOD_INVALID` | `reset_password` called with a delivery method other than `email` or `sms` |
| `HARD_STOP` | Returned by the hook integration layer when `check_pre_tool_use` denies a call |
| `MAX_TOKENS_EXCEEDED` | Specialist loop hit `max_tokens` stop reason before completing |
| `UNKNOWN_STOP_REASON` | Agent loop received an unrecognised `stop_reason` value |
| `SCHEMA_VALIDATION_EXHAUSTED` | Coordinator retry loop exhausted `MAX_RETRIES` without a valid classification |
| `UPSTREAM_ERROR` | Real integration (ITSM, LDAP) returned an error — stub never uses this code |

- The `"guidance"` field must be one sentence in imperative mood telling the agent what to do next — e.g. `"Call verify_identity before calling reset_password."` or `"Escalate to the security queue; do not retry."`.
- Never use `UPSTREAM_ERROR` in stub implementations — stubs must return realistic success responses or a domain-specific code, not infrastructure errors.

### PreToolUse Hook Integration

Every specialist event loop calls `check_pre_tool_use(tool_name, tool_input)` before sending any tool confirmation:

```python
allowed, deny_message = check_pre_tool_use(tool_name, tool_input)
if not allowed:
    # send deny_message back as tool result content
    # set escalate = True
    # break the loop — do not retry the denied call
```

- A denied call is never retried — it returns `{ "isError": true, "code": "HARD_STOP", "guidance": deny_message }` to the agent as the tool result, then the loop escalates.
- Adding a new pattern to `check_pre_tool_use` also requires a unit test in `tests/test_hooks/` that confirms the pattern fires on the target input and does not fire on a benign input.
