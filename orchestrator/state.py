"""Pipeline state: tracks outputs, iteration count, and escalation per area."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EscalationRecord:
    area: str
    fail_count: int = 0
    current_tier: int = 0       # index into ESCALATION_TIERS[category]
    model_history: list = field(default_factory=list)  # list of (model, effort) tried


@dataclass
class UsageInfo:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class AgentResult:
    role: str
    raw: str
    usage: UsageInfo
    sequence: str = ""          # e.g. "P1_01"
    filename: str = ""          # conversation/ filename


@dataclass
class PipelineState:
    project_root: Path
    iteration: int = 0          # REVIEWER/FIXER cycle count (max 3)
    high_issues_remain: bool = True
    cumulative_cost_usd: float = 0.0

    outputs: dict = field(default_factory=dict)
    # keys: "planner", "builder", "reviewer_1", "fixer_1", ...

    escalation_tracker: dict = field(default_factory=dict)
    # keys: "{category}:{area_key}" → EscalationRecord

    _sequence_counters: dict = field(default_factory=dict)
    # keys: role → current sequence int

    def next_sequence(self, role: str) -> str:
        """Return zero-padded sequence prefix, e.g. 'P1_01', and increment counter."""
        from config import PHASE
        phase = PHASE[role]
        count = self._sequence_counters.get(role, 0) + 1
        self._sequence_counters[role] = count
        return f"P{phase}_{count:02d}"

    def record_output(self, role: str, result: AgentResult) -> None:
        key = role if role not in ("reviewer", "fixer") else f"{role}_{self.iteration}"
        self.outputs[key] = result

    def get_escalation(self, category: str, area_key: str) -> EscalationRecord:
        key = f"{category}:{area_key}"
        if key not in self.escalation_tracker:
            self.escalation_tracker[key] = EscalationRecord(area=area_key)
        return self.escalation_tracker[key]
