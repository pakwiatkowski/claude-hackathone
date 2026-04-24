"""
Tools for fetching commit data from the GitHub REST API.
"""
import os
import urllib.request
import urllib.error
import json

GITHUB_TOOLS = [
    {
        "name": "fetch_commit_diff",
        "description": (
            "Fetches the unified diff for a commit from the GitHub API. "
            "Use this when you need the raw code changes for a commit SHA. "
            "Does NOT return binary file contents — those are skipped. "
            "Returns an object with fields: sha, message, author, files (list of "
            "{filename, status, additions, deletions, patch})."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sha": {
                    "type": "string",
                    "description": "The full or abbreviated commit SHA.",
                },
                "repo": {
                    "type": "string",
                    "description": "GitHub repo in owner/repo format.",
                },
            },
            "required": ["sha", "repo"],
        },
    },
    {
        "name": "fetch_file_content",
        "description": (
            "Fetches the current content of a file at a specific commit ref. "
            "Use this to get full file context around a changed section. "
            "Returns the decoded UTF-8 file content as a string. "
            "Fails gracefully on binary files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/repo format."},
                "path": {"type": "string", "description": "File path in the repo."},
                "ref": {"type": "string", "description": "Commit SHA or branch name."},
            },
            "required": ["repo", "path", "ref"],
        },
    },
]


def handle_github_tool(name: str, inputs: dict) -> dict:
    if name == "fetch_commit_diff":
        return _fetch_commit_diff(inputs["sha"], inputs["repo"])
    if name == "fetch_file_content":
        return _fetch_file_content(inputs["repo"], inputs["path"], inputs["ref"])
    return {"isError": True, "reason": f"Unknown GitHub tool: {name}"}


def _github_request(url: str) -> dict | str:
    token = os.environ.get("GITHUB_TOKEN", "")
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "claude-presentation-agent",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"isError": True, "reason": f"GitHub API {e.code}: {e.reason}", "url": url}


def _fetch_commit_diff(sha: str, repo: str) -> dict:
    data = _github_request(f"https://api.github.com/repos/{repo}/commits/{sha}")
    if isinstance(data, dict) and data.get("isError"):
        return data

    files = []
    for f in data.get("files", []):
        if not f.get("patch"):
            continue
        files.append(
            {
                "filename": f["filename"],
                "status": f["status"],
                "additions": f["additions"],
                "deletions": f["deletions"],
                "patch": f["patch"],
            }
        )

    return {
        "sha": data.get("sha", sha),
        "message": data.get("commit", {}).get("message", ""),
        "author": data.get("commit", {}).get("author", {}).get("name", ""),
        "files": files,
    }


def _fetch_file_content(repo: str, path: str, ref: str) -> dict:
    import base64

    data = _github_request(
        f"https://api.github.com/repos/{repo}/contents/{path}?ref={ref}"
    )
    if isinstance(data, dict) and data.get("isError"):
        return data

    encoding = data.get("encoding", "")
    content_raw = data.get("content", "")

    if encoding == "base64":
        try:
            decoded = base64.b64decode(content_raw).decode("utf-8")
            return {"path": path, "content": decoded}
        except (ValueError, UnicodeDecodeError):
            return {"isError": True, "reason": "Binary file — cannot decode as UTF-8"}

    return {"isError": True, "reason": f"Unexpected encoding: {encoding}"}
