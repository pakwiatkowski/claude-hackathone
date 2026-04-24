"""
IT Helpdesk Triage Agent — CLI entry point.

Usage:
  python src/main.py --ticket-id T-001 --body "I forgot my password" --user-id U-003 --channel portal

Environment:
  ANTHROPIC_API_KEY  required
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv


def _check_api_key() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        print("Set it in your environment or in a .env file.", file=sys.stderr)
        sys.exit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IT Helpdesk Triage Agent — classify, route, and auto-resolve tickets."
    )
    parser.add_argument("--ticket-id", required=True, help="Ticket identifier (e.g. T-001)")
    parser.add_argument("--body", required=True, help="Full ticket body text")
    parser.add_argument("--user-id", required=True, help="Submitting user ID (e.g. U-001)")
    parser.add_argument(
        "--channel",
        choices=["jira", "slack", "portal", "email"],
        default="portal",
        help="Arrival channel (default: portal)",
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output"
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    _check_api_key()
    args = _parse_args()

    from src.agents.coordinator import run_coordinator

    ticket = {
        "ticket_id": args.ticket_id,
        "body": args.body,
        "user_id": args.user_id,
        "channel": args.channel,
    }

    print(f"Processing ticket {ticket['ticket_id']} from {ticket['channel']}...", flush=True)

    result = run_coordinator(ticket)

    indent = 2 if args.pretty else None
    print(json.dumps(result, indent=indent))


if __name__ == "__main__":
    main()
