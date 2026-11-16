"""Central configuration: arXiv topics, taxonomy, and runtime knobs.

Everything a user is likely to tune lives here or in an environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "papers.json"
README_FILE = ROOT / "README.md"
ARCHIVE_DIR = ROOT / "archive"
CHART_FILE = ROOT / "assets" / "trend.svg"

# --- arXiv -----------------------------------------------------------------
# A paper matching several topics is tagged with all of them. When the daily
# cap is hit, new papers are taken round-robin across topics.
TOPICS = [
    {
        "key": "hitl",
        "label": "Human-in-the-loop",
        "query": (
            '(abs:"human-in-the-loop" OR abs:"human in the loop" '
            'OR abs:"interactive imitation learning" OR abs:"shared autonomy") '
            "AND (cat:cs.RO OR cat:cs.LG OR cat:cs.AI OR cat:cs.HC)"
        ),
        "max_results": 30,
    },
    {
        "key": "industrial_rl",
        "label": "Industrial RL",
        "query": (
            'abs:"reinforcement learning" '
            'AND (abs:industrial OR abs:manufacturing OR abs:factory OR abs:"process control") '
            "AND (cat:cs.LG OR cat:cs.RO OR cat:cs.AI OR cat:eess.SY)"
        ),
        "max_results": 30,
    },
    {
        "key": "robotics",
        "label": "Robotics",
        "query": "cat:cs.RO",
        "max_results": 100,
    },
]
TOPIC_LABELS = {t["key"]: t["label"] for t in TOPICS}

# Max number of *new* papers sent to the LLM per run (cost guard).
MAX_NEW_PER_RUN = int(os.environ.get("MAX_NEW_PER_RUN") or 50)
# Multiplies each topic's max_results; raise it for a one-off backfill.
FETCH_MULTIPLIER = int(os.environ.get("FETCH_MULTIPLIER") or 1)

# --- LLM -------------------------------------------------------------------
LLM_MODEL = os.environ.get("LLM_MODEL") or "claude-opus-5-5"
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY") or 4)

# (key, display name). The key is what the LLM returns and what is stored.
CATEGORIES = [
    ("manipulation", "Manipulation"),
    ("locomotion_nav", "Locomotion & Navigation"),
    ("vla", "Foundation Models / VLA"),
    ("hitl", "Human-in-the-loop"),
    ("industrial_rl", "Industrial RL & Control"),
    ("sim2real", "Simulation & Sim2Real"),
    ("perception", "Perception & Mapping"),
    ("other", "Other"),
]
CATEGORY_NAME = dict(CATEGORIES)

# --- README ----------------------------------------------------------------
README_RECENT_DAYS = 3  # full listing for the last N days
README_TOP_DAYS = 7  # window for the "top picks" table
README_TOP_N = 10
