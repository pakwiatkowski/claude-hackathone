# /new-specialist — Scaffold a new specialist subagent

Scaffold a new specialist agent that follows the exact pattern established in
`src/agents/specialists/password_reset.py` and `src/tools/password_reset_tools.py`.

Arguments: `$ARGUMENTS` — the specialist domain, e.g. `network`, `hardware`, `software`.

## Steps

1. Determine the specialist name from `$ARGUMENTS`. Normalise to snake_case.
   If empty, ask: "What domain is this specialist for? (e.g. network, hardware, software)"

2. Ask the user for the 4 tool names this specialist will need. Remind them the mandate
   caps at 4–5 tools per specialist (ADR-001). Suggest sensible defaults based on the domain:
   - network → `check_connectivity`, `run_diagnostic`, `lookup_device`, `escalate_outage`
   - hardware → `lookup_asset`, `check_warranty`, `create_dispatch`, `close_ticket`
   - software → `lookup_license`, `check_install_status`, `push_patch`, `close_ticket`

3. Create `src/tools/<name>_tools.py` using the template from `src/tools/password_reset_tools.py`:
   - `_tool_error` helper
   - Stub data store
   - One function + one `*_SCHEMA` dict per tool
   - `<NAME>_TOOL_SCHEMAS` list
   - `<NAME>_TOOL_HANDLERS` dict

4. Create `src/agents/specialists/<name>.py` using the template from
   `src/agents/specialists/password_reset.py`:
   - `SPECIALIST_SYSTEM_PROMPT` tailored to the domain
   - `run_<name>_specialist(ticket_id, user_id, issue_summary)` function
   - Imports from the new tool file

5. Add a routing entry in `src/agents/coordinator.py`:
   - Import the new specialist
   - Add the new `category` value to the auto-resolve condition check
   - Update the comment listing available specialists

6. Add `category` to `TicketClassification` literal in `src/models/schemas.py` if it's new.

7. Print a summary of files created/modified and the routing condition added.
