# /reasoning-trace — Visualise a coordinator reasoning chain

Parse and display the `reasoning_chain` JSON from a coordinator result or from
the in-memory ticket store, in a human-readable step-by-step trace.

Arguments: `$ARGUMENTS` — either:
  - A raw JSON string (paste the coordinator result)
  - A ticket ID to look up in `src/tools/coordinator_tools._TICKET_STORE`
  - A file path to a saved JSON result

## Steps

1. Determine input source from `$ARGUMENTS`:
   - Starts with `{` → parse as inline JSON
   - Starts with `T-` → extract reasoning_chain from the ticket store by running:
     ```python
     python -c "
     from src.tools.coordinator_tools import _TICKET_STORE
     import json
     t = _TICKET_STORE.get('$ARGUMENTS', {})
     print(json.dumps(t.get('reasoning_chain', '[]')))
     "
     ```
   - Otherwise treat as file path and read the JSON from disk.

2. Parse the `reasoning_chain` field (a JSON-encoded array of step dicts).

3. Render each step as a numbered block:
   ```
   ── Step 1: classify_ticket ──────────────────────────────
   Input : {body: "...", channel: "portal", user_id: "U-003"}
   Output: priority=P3 · category=password_reset · confidence=0.82
           auto_resolvable=true
           reasoning: "Category signals for 'password_reset': ['locked out', 'password']"

   ── Step 2: lookup_user ──────────────────────────────────
   Input : {user_id: "U-003"}
   Output: account_status=locked · vip_flag=false · department=HR

   ── Step 3: route_ticket ─────────────────────────────────
   ...
   ```

4. After all steps, print a summary footer:
   ```
   ─────────────────────────────────────────────────────────
   Decision  : auto_resolved
   Retries   : 0  (no validation errors)
   Hard stops: 0
   Ticket ID : T-001
   ```

5. If `retry_count > 0`, highlight the retry steps with ⚠ and show the
   validation error that caused each retry.

6. If a hard stop was triggered, show it with a 🛑 marker and the deny message.
