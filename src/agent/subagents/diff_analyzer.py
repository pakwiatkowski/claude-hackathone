"""
Diff Analyzer subagent: reads a raw git diff and produces a structured summary
of what changed, why it likely changed, and what impact it has.

Does NOT inherit coordinator context — all context must be in the prompt.
"""
import anthropic
import json

SYSTEM = """
You are a code diff analyst. Given a raw git diff and commit message, produce a
structured JSON analysis. Be factual and concise. Do not invent intent beyond
what the diff shows.

Output ONLY valid JSON matching this schema:
{
  "summary": "<one sentence describing the overall change>",
  "changed_areas": ["<area1>", "<area2>"],
  "key_changes": [
    {"file": "<path>", "type": "<added|removed|modified>", "description": "<what changed>"}
  ],
  "impact": "<none|low|medium|high>",
  "impact_reason": "<brief explanation>",
  "presentation_angle": "<one sentence: what story should the slides tell about this commit>"
}
"""


def run(prompt: str, client: anthropic.Anthropic) -> dict:
    """
    Analyzes the diff described in `prompt`.
    Returns a dict matching the schema above.
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "isError": True,
            "reason": "Failed to parse diff analysis JSON",
            "raw": text,
        }
