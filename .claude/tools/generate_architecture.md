You are a software architect. Analyze the project provided and generate a single self-contained HTML file that visually represents its architecture.

## What to analyze
- Entry points, services, and modules
- Data flow between components
- External dependencies and integrations
- Agent/subagent boundaries (if agentic)
- Storage, queues, and external APIs
- Authentication and permission layers

## HTML output requirements
The file must be a single .html with all CSS and JS inline. Build it as an interactive diagram using one of:
- SVG with clickable nodes (preferred for clean architectures)
- vis-network or D3 force graph (preferred for complex dependency graphs)

### Visual rules
- Group components by layer: inbound → orchestration → services → storage
- Color-code by component type: agents = purple, tools/APIs = blue, storage = teal, external = gray, HITL/human = amber
- Every node must be clickable and show a tooltip or side panel with: component name, responsibility, inputs, outputs, and tech stack
- Draw directional arrows for data flow; label arrows with the payload or event type
- Use a legend

### Interactivity
- Click a node to highlight its direct connections and dim everything else
- A search/filter input that highlights matching nodes
- A layer toggle: show/hide inbound, orchestration, services, storage layers independently
- Reset button to clear highlights

### Layout
- Fixed 1200px wide canvas (scrollable if tall)
- Dark background (#0f1117) with light node labels
- Compact but readable — no overlapping labels

## Output
Return ONLY the complete HTML file. No explanation, no markdown fences, no preamble.
Start directly with <!DOCTYPE html>.