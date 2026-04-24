"""
Tools for writing the final presentation output.
"""
import os
import pathlib

OUTPUT_DIR = pathlib.Path("output")

PRESENTATION_TOOLS = [
    {
        "name": "write_presentation",
        "description": (
            "Saves the finished Marp Markdown slide deck to disk. "
            "Call this ONCE at the end, after all slides are finalized. "
            "Do NOT call it with partial or draft content. "
            "Returns the path of the written file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The complete Marp Markdown content.",
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Output filename (without directory). "
                        "Defaults to 'presentation.md' if omitted."
                    ),
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "delegate_to_subagent",
        "description": (
            "Delegates a task to a specialist subagent. "
            "Available subagents:\n"
            "- 'diff_analyzer': Analyzes a raw git diff and returns structured JSON. "
            "Pass the full diff text plus commit message in the prompt.\n"
            "- 'slide_writer': Writes a Marp slide deck from a diff analysis. "
            "Pass the diff analysis JSON plus commit metadata in the prompt.\n"
            "Each subagent runs in isolation — include ALL context in the prompt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subagent": {
                    "type": "string",
                    "enum": ["diff_analyzer", "slide_writer"],
                    "description": "Which subagent to call.",
                },
                "prompt": {
                    "type": "string",
                    "description": "Self-contained prompt with all required context.",
                },
            },
            "required": ["subagent", "prompt"],
        },
    },
]


def handle_presentation_tool(name: str, inputs: dict) -> dict:
    if name == "write_presentation":
        return _write_presentation(
            inputs["content"], inputs.get("filename", "presentation.md")
        )
    return {"isError": True, "reason": f"Unknown presentation tool: {name}"}


def _write_presentation(content: str, filename: str) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = pathlib.Path(filename).name
    out_path = OUTPUT_DIR / safe_name
    out_path.write_text(content, encoding="utf-8")
    return {"path": str(out_path), "bytes_written": len(content.encode())}
