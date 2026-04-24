# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a greenfield agentic intake system built on the **Claude Agent SDK** (Python or TypeScript). The domain and implementation have not been chosen yet — the specification in `docs/agentic-solution.md` outlines six candidate domains (professional services routing, IT helpdesk, insurance claims, code review, compliance/KYC, sales lead routing).

Auth: set `ANTHROPIC_API_KEY` in environment.

SDK docs:
- Overview: docs.claude.com/en/api/agent-sdk/overview
- Python: docs.claude.com/en/api/agent-sdk/python
- 
- TypeScript: docs.claude.com/en/api/agent-sdk/typescript
- Custom tools: docs.claude.com/en/api/agent-sdk/custom-tools
- Permissions/hooks: docs.claude.com/en/api/agent-sdk/permissions

## Target Architecture

**Coordinator + Specialist Subagent pattern:**

- **Coordinator agent** — ingests requests, classifies, enriches with context, routes to a specialist. Logs the full reasoning chain (not just the answer) so every decision is replayable. Wraps structured output in a validation-retry loop: schema validation → feed specific error back to Claude → retry up to N times → log retry count and error type.
- **Specialist agents** (Task subagents) — domain-specific, isolated contexts. Each specialist receives only what is explicitly passed in its Task prompt; it does **not** inherit the coordinator's context. Each specialist has its own focused tool set (target: 4–5 tools; reliability drops beyond that).

**Tool design constraints:**
- Every tool needs a knowledge-lookup, system-of-record read, and at least one write/action tool.
- Tool descriptions must state what the tool does *not* do, including input formats, edge cases, and example queries.
- Errors must return structured: `{ isError: true, reasonCode, guidance }` so the agent can recover without parsing a string.

**Human-in-the-loop (The Brake):**
- Escalation rules are explicit: `category + confidence_threshold + dollar_impact_bucket` — not vague ("when unsure").
- A `PreToolUse` hook acts as a **hard stop** for high-risk patterns (PII exfiltration, actions on frozen accounts, known-bad routes). This is deterministic, not AI-driven.
- The escalation path is a **slow stop** (approval flow); the hook is a **hard stop**.

**Adversarial evaluation (The Attack):**
- Labeled eval set covering prompt injection in request bodies, ambiguous asks, fake-urgency requests, and routine-looking requests with legal exposure.
- Probes for: misrouting, context leakage, mis-escalation.

**Eval harness (The Scorecard):**
- Labeled dataset across all categories with expected decisions including escalations.
- Metrics: accuracy, precision per category, escalation rate (correct vs. needless), adversarial-pass rate, false-confidence rate.
- Stratified sampling to prevent easy categories from dominating the score.
- Runs in CI.

## What the Agent Must Never Do

Defined per-domain in the Mandate (challenge 1 in `docs/agentic-solution.md`). Before implementing, this must be written down explicitly — it is the primary governance artifact.
