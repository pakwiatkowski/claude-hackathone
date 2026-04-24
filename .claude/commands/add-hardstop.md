# /add-hardstop — Register a new hard-stop pattern

Add a new deterministic blocking rule to `src/hooks/pre_tool_use.py`.
Hard stops are synchronous, LLM-free — they run before every tool confirmation.

Arguments: `$ARGUMENTS` — description of the pattern to block, e.g.
`block reset_password when account department is Legal`.

## Steps

1. Read `src/hooks/pre_tool_use.py` to understand the existing pattern structure.

2. Parse `$ARGUMENTS` to determine the block type. Classify into one of:
   - **tool_name match** — block a specific tool name or prefix
   - **input_field condition** — block when a field value meets a condition
   - **regex pattern** — block when any string field matches a regex
   - **account status** — block based on account metadata lookup

3. Ask clarifying questions if the pattern is ambiguous:
   - Which tool(s) does this apply to? (or "all tools")
   - What exact condition triggers the block?
   - What deny message should the agent receive?

4. Check for overlap with existing rules. If the new rule is a subset of an existing
   one, point that out before adding.

5. Add the rule to `check_pre_tool_use` in `src/hooks/pre_tool_use.py`:
   - New rules go in a clearly numbered comment block
   - Include the deny message as a descriptive string
   - Keep it synchronous — no I/O, no LLM calls

6. Add a corresponding test case description to `docs/mandate.md` under
   "What the Agent Never Touches" if the pattern represents a new policy category.

7. Run a smoke test:
   ```
   python -c "from src.hooks.pre_tool_use import check_pre_tool_use; print(check_pre_tool_use('test_tool', {}))"
   ```
   Confirm `(True, '')` for a benign call.

8. Show the diff of what was added.
