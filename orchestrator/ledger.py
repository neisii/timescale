"""Token and cost tracking across the pipeline run."""

from dataclasses import dataclass, field
from config import PRICE_PER_MTOK, ESTIMATED
from state import UsageInfo


@dataclass
class LedgerEntry:
    role: str
    sequence: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float


class TokenLedger:
    def __init__(self):
        self.entries: list[LedgerEntry] = []

    def record(self, role: str, sequence: str, usage: UsageInfo) -> float:
        """Calculate cost, record entry, return cost_usd for this call."""
        price = PRICE_PER_MTOK.get(usage.model, PRICE_PER_MTOK[list(PRICE_PER_MTOK)[1]])
        cost = (
            usage.input_tokens      * price["input"]  / 1_000_000
            + usage.output_tokens   * price["output"] / 1_000_000
            + usage.cache_read_tokens * price["cache"] / 1_000_000
        )
        self.entries.append(LedgerEntry(
            role=role,
            sequence=sequence,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cost_usd=cost,
        ))
        return cost

    @property
    def total_cost(self) -> float:
        return sum(e.cost_usd for e in self.entries)

    @property
    def total_input_tokens(self) -> int:
        return sum(e.input_tokens for e in self.entries)

    @property
    def total_output_tokens(self) -> int:
        return sum(e.output_tokens for e in self.entries)

    def drift_report(self) -> str:
        """Compare actuals vs cost-estimation.md estimates."""
        lines = ["## 추정 대비 실측 (전체 누계)"]
        lines.append("")
        lines.append("| Agent | 입력(추정) | 입력(실측) | 출력(추정) | 출력(실측) | 오차 |")
        lines.append("|---|---|---|---|---|---|")

        for role, est in ESTIMATED.items():
            actual_entries = [e for e in self.entries if e.role == role]
            if not actual_entries:
                continue
            act_in  = sum(e.input_tokens for e in actual_entries)
            act_out = sum(e.output_tokens for e in actual_entries)
            est_in  = est["input"]
            est_out = est["output"]
            drift_in  = f"{(act_in  - est_in)  / est_in  * 100:+.1f}%" if est_in  else "—"
            drift_out = f"{(act_out - est_out) / est_out * 100:+.1f}%" if est_out else "—"
            lines.append(
                f"| {role} | {est_in:,} | {act_in:,} | {est_out:,} | {act_out:,} "
                f"| in:{drift_in} out:{drift_out} |"
            )
        return "\n".join(lines)

    def summary_report(self) -> str:
        lines = [
            "── Token & Cost Report ──────────────────────────────────────",
            f"  총 입력 토큰  : {self.total_input_tokens:,}",
            f"  총 출력 토큰  : {self.total_output_tokens:,}",
            f"  총 비용 (USD) : ${self.total_cost:.4f}",
            "─" * 60,
        ]
        for e in self.entries:
            lines.append(
                f"  {e.sequence} {e.role:<10} {e.model:<30} "
                f"in:{e.input_tokens:>7,} out:{e.output_tokens:>6,}  ${e.cost_usd:.4f}"
            )
        lines.append("─" * 60)
        return "\n".join(lines)
