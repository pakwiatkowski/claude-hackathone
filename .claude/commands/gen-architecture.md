# /gen-architecture — Generate the architecture diagram

Read the `docs/` folder and `src/` directory, then write a self-contained HTML
architecture diagram to `docs/architecture.html`.

Arguments: `$ARGUMENTS` — optional output path (default: `docs/architecture.html`).

## Steps

1. **Resolve output path**
   - If `$ARGUMENTS` is non-empty, use it as the output path.
   - Otherwise default to `docs/architecture.html`.

2. **Delegate to the architecture-diagram agent**
   Use the `architecture-diagram` subagent to read the codebase and produce
   the diagram. Pass the resolved output path so the agent writes to the right
   location.

   The agent will:
   - Glob `src/**/*.py` and `docs/**/*`
   - Read every source file and doc
   - Extract agents, models, tools, hooks, schemas, config constants, data flow
   - Write a dark-themed, self-contained HTML file

3. **Confirm success**
   After the agent completes, verify the output file exists and print:

   ```
   ✓ docs/architecture.html generated
     Components: <N> (agents + tools + hooks + schemas)
     Size: <KB>
     Open with: start docs/architecture.html   (Windows)
                open docs/architecture.html    (macOS)
   ```

4. **On failure** — if the agent errors or the file was not written, show the
   error and suggest running with `/gen-architecture` again after fixing the
   reported issue.
