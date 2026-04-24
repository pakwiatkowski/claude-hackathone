# /triage — Run a ticket through the coordinator

Given a natural-language description of an IT support issue, run it through the coordinator agent and present the result in a readable summary.

Arguments: `$ARGUMENTS` — free-form description of the ticket. If no argument, ask the user for ticket body, user ID, and channel.

## Steps

1. Parse `$ARGUMENTS`. Extract or prompt for:
   - `body` — the ticket text (required)
   - `user_id` — default to `U-001` if not specified
   - `channel` — default to `portal` if not specified
   - `ticket_id` — generate as `T-<timestamp>` if not provided

2. Run the coordinator:
   ```
   python src/main.py --ticket-id <ticket_id> --body "<body>" --user-id <user_id> --channel <channel> --pretty
   ```

3. Parse the JSON output and present a human-readable summary:
   - Priority + category + confidence (with a visual confidence bar: ████░░ for 0.7)
   - Decision: AUTO-RESOLVED / ROUTED to `<queue>` / ESCALATED (reason)
   - Retry count (flag with ⚠ if > 0)
   - One-line reasoning excerpt from reasoning_chain

4. If the run fails (non-zero exit or missing API key), diagnose and show the fix.

Example output format:
```
Ticket T-20260424-001 · portal · U-001
────────────────────────────────────────
Priority  : P3
Category  : password_reset
Confidence: ████████░░ 0.82
Decision  : AUTO-RESOLVED ✓
Retries   : 0
```
