# /new-tool — Add a tool to an existing agent

Add a new tool (function + JSON schema + handler registration) to an existing
coordinator or specialist tool file, following the established pattern.

Arguments: `$ARGUMENTS` — e.g. `coordinator notify_user` or `password_reset send_sms`.
Format: `<agent> <tool_name>`. If missing, ask.

## Steps

1. Parse `$ARGUMENTS` into `agent` and `tool_name`.
   Valid agents: `coordinator`, `password_reset`, or any specialist name found in `src/tools/`.

2. Determine the target file: `src/tools/<agent>_tools.py`.
   Read the file to understand the existing pattern (stubs, helper functions, registry dicts).

3. Check the tool count in the target file. If already at 4 tools, warn:
   > ⚠ This agent already has 4 tools. ADR-001 notes reliability drops beyond 4–5.
   > Add anyway? (y/n)

4. Ask for:
   - One-sentence description of what the tool does
   - One-sentence of what it does NOT do (required for schema `description` field)
   - Required input fields (name, type, description) — collect up to 5
   - Return shape on success

5. Generate and append to the tool file:
   - `<TOOL_NAME>_SCHEMA` dict with full `input_schema`
   - `def <tool_name>(**kwargs)` stub function that returns a success dict or `_tool_error(...)`
   - Entry in `<AGENT>_TOOL_SCHEMAS` list
   - Entry in `<AGENT>_TOOL_HANDLERS` dict

6. Run a quick syntax check:
   ```
   python -c "from src.tools.<agent>_tools import <AGENT>_TOOL_SCHEMAS; print('OK')"
   ```

7. Report the new tool name, its position in the tool list, and a one-line usage example.
