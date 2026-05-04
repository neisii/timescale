"""Data models for REVIEWER output parsing."""

from dataclasses import dataclass, field


@dataclass
class Issue:
    description: str
    severity: str       # "high" | "medium" | "low"
    category: str       # "A" | "B" | "C"
    affected_files: list = field(default_factory=list)

    @property
    def is_high(self) -> bool:
        return self.severity.lower() == "high"


@dataclass
class ReviewResult:
    issues: list = field(default_factory=list)   # list[Issue]
    raw_text: str = ""
    parse_error: bool = False   # True if regex fallback was used

    @property
    def has_high_issues(self) -> bool:
        if self.parse_error:
            return "high" in self.raw_text.lower()
        return any(i.is_high for i in self.issues)

    @property
    def high_issues(self) -> list:
        return [i for i in self.issues if i.is_high]

    @property
    def dominant_category(self) -> str:
        """Return the most complex category among High issues (C > B > A)."""
        high_cats = [i.category.upper() for i in self.high_issues if i.category]
        if "C" in high_cats:
            return "C"
        if "B" in high_cats:
            return "B"
        return "A"


@dataclass
class FixerDecision:
    config: dict          # full agent config {model, thinking, max_tokens}
    category: str
    escalation_tier: int = 0
    escalated: bool = False

    @property
    def model(self) -> str:
        return self.config["model"]

    @property
    def thinking(self) -> str | None:
        return self.config.get("thinking")
