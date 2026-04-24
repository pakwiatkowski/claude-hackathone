"""
Slide Writer subagent: takes a diff analysis and commit metadata, and writes
a complete Marp slide deck in Markdown.

Does NOT inherit coordinator context — all context must be in the prompt.
"""
import anthropic

SYSTEM = """
You are a technical presentation writer. Given a structured diff analysis and
commit metadata, write a complete Marp slide deck in Markdown.

Rules:
- Use Marp front-matter: --- marp: true theme: default paginate: true ---
- 5–8 slides max. Quality over quantity.
- Slide 1: title slide with repo, author, date, and one-line summary.
- Slide 2: "What changed" — bullet list of key files/areas.
- Slides 3–N: one slide per key change area with code snippets if relevant.
- Last slide: impact assessment and any follow-up action items.
- Use ```diff fences for code changes, not raw text.
- Keep each slide under 8 bullet points. Prefer short, scannable text.
- Output ONLY the Marp Markdown, no surrounding explanation.
"""


def run(prompt: str, client: anthropic.Anthropic) -> str:
    """
    Generates a Marp Markdown slide deck from the prompt.
    Returns the raw Marp Markdown string.
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
