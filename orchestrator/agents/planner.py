"""PLANNER agent — Sonnet 4.6, thinking=high."""

from pathlib import Path

from agents.base import BaseAgent
from config import SPEC_MD, PROJECT_ROOT
from state import PipelineState, AgentResult
from ledger import TokenLedger
import agent_io.conversation as conv_log
import agent_io.cost as cost_log


class PlannerAgent(BaseAgent):
    ROLE = "planner"

    def __init__(self, ledger: TokenLedger, project_root: Path = PROJECT_ROOT):
        super().__init__(project_root)
        self.ledger = ledger

    def run(self, state: PipelineState) -> AgentResult:
        task = "Architecture-Design"
        seq  = state.next_sequence(self.ROLE)

        spec = SPEC_MD.read_text(encoding="utf-8")
        prompt = f"""당신은 PLANNER입니다. 아래 spec.md를 분석하여 전체 시스템 설계를 수행하십시오.

## spec.md

{spec}

---

설계 완료 후 다음을 반드시 수행하십시오:
1. `plan.md`를 프로젝트 루트에 작성하십시오 (세션 간 연결용 진입점).
2. `docs/architecture.md`, `docs/data-flow.md`, `docs/tradeoff.md`, `docs/failure-case.md`, `docs/kafka-design.md`를 작성하십시오.
3. AGENTS.md [섹션 10]에 정의된 출력 형식을 따르십시오.
"""

        print(f"\n[P1] PLANNER — {seq} 설계 시작")
        response, usage = self._run(prompt)

        cost_usd = self.ledger.record(self.ROLE, seq, usage)
        state.cumulative_cost_usd += cost_usd

        conv_path = conv_log.save(
            role=self.ROLE, sequence=seq, iteration=state.iteration,
            task_description=task, content=response,
        )
        cost_log.save(
            role=self.ROLE, sequence=seq, iteration=state.iteration,
            task_description=task, usage=usage,
            cost_usd=cost_usd, cumulative_usd=state.cumulative_cost_usd,
        )

        result = AgentResult(
            role=self.ROLE, raw=response, usage=usage,
            sequence=seq, filename=conv_path.name,
        )
        state.record_output(self.ROLE, result)
        print(f"    → {conv_path.name}  (${cost_usd:.4f})")
        return result
