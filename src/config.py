import os

MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3
CONFIDENCE_THRESHOLD = 0.70
HIGH_IMPACT_DOLLAR = 10_000

QUEUES = ["tier1", "tier2", "networking", "security", "hardware"]

SLA_HOURS = {
    "P1": 1,
    "P2": 4,
    "P3": 8,
    "P4": 24,
}

QUEUE_SLA_HOURS = {
    "tier1": 4,
    "tier2": 8,
    "networking": 4,
    "security": 2,
    "hardware": 24,
}

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
