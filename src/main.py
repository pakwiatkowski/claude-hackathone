"""
Entry point invoked by GitHub Actions.
Reads commit context from environment variables and runs the coordinator agent.
"""
import os
import sys
import anthropic
from src.agent.coordinator import run as run_coordinator


def _commit_info_from_env() -> dict:
    return {
        "sha": os.environ["COMMIT_SHA"],
        "message": os.environ.get("COMMIT_MESSAGE", ""),
        "author": os.environ.get("COMMIT_AUTHOR", ""),
        "timestamp": os.environ.get("COMMIT_TIMESTAMP", ""),
        "repo": os.environ["GITHUB_REPOSITORY"],
    }


def main():
    commit_info = _commit_info_from_env()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    result = run_coordinator(commit_info, client)
    print(result)


if __name__ == "__main__":
    sys.exit(main())
