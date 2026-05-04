"""Model constants, pricing, paths, and phase configuration."""

from pathlib import Path

# ── Project root ───────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent

# ── Model IDs ─────────────────────────────────────────────────────────────────

OPUS   = "claude-opus-4-7"
SONNET = "claude-sonnet-4-6"
HAIKU  = "claude-haiku-4-5-20251001"

# ── Extended thinking budgets (tokens) ────────────────────────────────────────
# Thinking tokens are billed as output tokens ($15/MTok for Sonnet).
# max_tokens for each agent must exceed its budget.

THINKING_BUDGETS = {
    "low":   2_048,
    "medium": 8_192,
    "high":  16_000,
    "xhigh": 28_000,
    "max":   32_000,
}

# ── Per-agent configurations ───────────────────────────────────────────────────
#
# thinking: None | "low" | "medium" | "high" | "xhigh" | "max"
# Haiku does not support extended thinking; always set thinking=None for Haiku.

AGENT_CONFIGS = {
    "planner":  {"model": SONNET, "thinking": "high",   "max_tokens": 32_000},
    "builder":  {"model": SONNET, "thinking": "medium", "max_tokens": 32_000},
    "reviewer": {"model": SONNET, "thinking": None,     "max_tokens": 8_000},
}

# FIXER escalation tiers per issue category (A = simple → C = complex).
# Each entry is a full agent config dict; escalate by incrementing tier index.

FIXER_ESCALATION: dict[str, list[dict]] = {
    "A": [
        {"model": HAIKU,  "thinking": None,     "max_tokens": 8_000},   # tier 0
        {"model": SONNET, "thinking": "low",    "max_tokens": 12_000},  # tier 1
        {"model": SONNET, "thinking": "medium", "max_tokens": 16_000},  # tier 2
    ],
    "B": [
        {"model": SONNET, "thinking": None,     "max_tokens": 8_000},   # tier 0
        {"model": SONNET, "thinking": "medium", "max_tokens": 16_000},  # tier 1
    ],
    "C": [
        {"model": SONNET, "thinking": "low",    "max_tokens": 12_000},  # tier 0
        {"model": SONNET, "thinking": "high",   "max_tokens": 32_000},  # tier 1
    ],
}

# ── Pricing (USD per million tokens, 2026-05-04) ──────────────────────────────

PRICE_PER_MTOK = {
    OPUS:   {"input": 5.0,  "cache": 0.50, "output": 25.0},
    SONNET: {"input": 3.0,  "cache": 0.30, "output": 15.0},
    HAIKU:  {"input": 1.0,  "cache": 0.10, "output":  5.0},
}

# Expected tokens from cost-estimation.md (for drift comparison)
ESTIMATED = {
    "planner":  {"input": 10_800, "output": 13_500},
    "builder":  {"input": 18_000, "output":  9_000},
    "reviewer": {"input": 34_000, "output":  4_000},
    "fixer":    {"input": 35_000, "output":  4_500},
}

# ── Role files ────────────────────────────────────────────────────────────────

ROLE_FILES = {
    "planner":  PROJECT_ROOT / "role" / "PLANNER.md",
    "builder":  PROJECT_ROOT / "role" / "BUILDER.md",
    "reviewer": PROJECT_ROOT / "role" / "REVIEWER.md",
    "fixer":    PROJECT_ROOT / "role" / "FIXER.md",
}

AGENTS_MD = PROJECT_ROOT / "AGENTS.md"
SPEC_MD   = PROJECT_ROOT / "spec.md"
PLAN_MD   = PROJECT_ROOT / "plan.md"

# ── Output directories ────────────────────────────────────────────────────────

CONVERSATION_DIR = PROJECT_ROOT / "conversation"
COST_DIR         = PROJECT_ROOT / "cost"
COST_ESTIMATION  = COST_DIR / "cost-estimation.md"

# ── Phase numbers ─────────────────────────────────────────────────────────────

PHASE = {"planner": 1, "builder": 2, "reviewer": 3, "fixer": 4}

# ── Pipeline limits ───────────────────────────────────────────────────────────

MAX_ITERATIONS = 3
