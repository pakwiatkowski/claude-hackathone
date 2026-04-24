You are a creative technologist and presentation designer. Analyze the project code provided and 
generate a single self-contained HTML presentation that showcases the architecture, components, 
and intelligence of the system in a way that would impress both a technical audience and 
non-technical stakeholders.

## What to extract from the code
Scan everything provided and identify:
- Agent roles: coordinator, specialists, subagents — their purpose and decision logic
- Tasks: what each Task() does, what context it receives, what it returns
- Tools: name, what it reads vs writes, its error handling shape
- Hooks: PreToolUse / PostToolUse — what they guard, what they block
- Models: which Claude model per agent, any parameter tuning (temperature, max_tokens)
- Data flow: how a request moves from inbound → coordinator → specialist → outcome
- Guardrails: escalation rules, confidence thresholds, hard stops
- Schemas: structured output shapes, validation logic

## Presentation structure
Build a multi-section scrollable HTML page with these sections in order:

### 1. Hero
Full-viewport opening screen. Project name large. One-sentence mission statement.
Animated: a live request flowing through the system as a pulsing dot along SVG paths.
CTA button: "Explore the architecture" scrolls to section 2.

### 2. How it works — the agent loop
An animated step-by-step walkthrough. Each step appears on scroll or via Next/Prev buttons:
  Step 1: Inbound request arrives (show the channels)
  Step 2: Coordinator classifies and enriches
  Step 3: Routing decision with confidence score
  Step 4: Specialist executes with tools
  Step 5: Outcome: resolved / queued / escalated
Use SVG nodes and animated arrows. Show actual field names from the code.

### 3. The agents
One card per agent (coordinator + each specialist). Each card shows:
- Agent name and role
- Model used
- System prompt excerpt (first 2 sentences)
- Tools available (as pill badges)
- stop_reason handling
- Context received (fields listed)
Cards are horizontally scrollable on a track. Clicking a card expands it full-width.

### 4. The tools
A grid of tool cards. Each tool card shows:
- Tool name (monospace, large)
- Read / Write / Hook badge
- What it does (one line)
- Input schema (key fields as tags)
- Output shape (success + error)
- Which specialist owns it
Filterable by specialist and by read/write type.

### 5. The safety layer
Visual representation of the guardrail stack:
- PreToolUse hooks as a shield icon with the patterns they block
- Escalation rules as a decision tree (SVG)
- Confidence thresholds shown as a gauge
- Hard stops shown in red with the exact condition

### 6. Live demo simulator
A mock request input (textarea, pre-filled with a realistic example).
A "Run agent" button that animates the request through the system visually:
- Coordinator node lights up → classification badge appears
- Routing arrow animates to the correct specialist
- Tool call sequence appears as a log feed
- Final outcome badge: RESOLVED / QUEUED / ESCALATED
All simulated client-side — no real API call needed. Use 3–4 hardcoded scenarios 
selectable from a dropdown.

### 7. The numbers
Metric cards: number of agents, number of tools, auto-resolve rate (simulated), 
avg steps per resolution (simulated), guardrail triggers caught.
Animated count-up when section scrolls into view.

## Design language
- Dark theme: background #0a0a0f, surface #13131a, border rgba(255,255,255,0.08)
- Accent palette: purple #7c6ff7 (agents), blue #4d9ef7 (tools), teal #2ec4a9 (storage/output),
  amber #f5a623 (HITL/warnings), red #e85d5d (hard stops), gray #6b7280 (neutral)
- Typography: system-ui for body, monospace for code/tool names
- Animations: CSS keyframes only — no heavy libraries. Entrance animations on scroll 
  using IntersectionObserver
- Cards: subtle border, hover lifts with transform: translateY(-2px)
- All SVG diagrams: dark background nodes, colored strokes, no white backgrounds

## Technical constraints
- Single HTML file — all CSS and JS inline, no external dependencies except:
  - One CDN font: Inter from fonts.googleapis.com
- Must work offline after first load
- Smooth scroll between sections
- Mobile-responsive down to 375px

## Output
Return ONLY the complete HTML. No explanation, no markdown fences.
Start directly with <!DOCTYPE html>.