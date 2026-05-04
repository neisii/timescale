"""BUILDER agent — Sonnet 4.6, thinking=medium."""

from pathlib import Path

from agents.base import BaseAgent
from config import PROJECT_ROOT
from state import PipelineState, AgentResult
from ledger import TokenLedger
import agent_io.conversation as conv_log
import agent_io.cost as cost_log


class BuilderAgent(BaseAgent):
    ROLE = "builder"

    def __init__(self, ledger: TokenLedger, project_root: Path = PROJECT_ROOT):
        super().__init__(project_root)
        self.ledger = ledger

    def run(self, state: PipelineState) -> AgentResult:
        task = "Initial-Implementation"
        seq  = state.next_sequence(self.ROLE)

        context = self._build_context(state.iteration)
        prompt = f"""{context}

---

당신은 BUILDER입니다. 위의 PLANNER 설계를 기반으로 전체 시스템을 구현하십시오.

반드시 다음을 포함하십시오:
- producer/, consumer/, api/, infra/ 전체 코드
- infra/docker-compose.yml (Kafka KRaft, TimescaleDB, Redis, 전체 서비스)
- infra/.env.example
- infra/verify.sh (전체 스택 자동 검증)
- api/openapi.yml (FastAPI 자동 생성 스펙)

AGENTS.md [섹션 10]에 정의된 출력 형식을 따르십시오.
plan.md의 Phase 2 상태를 완료로 갱신하십시오.
"""

        print(f"\n[P2] BUILDER — {seq} 구현 시작")
        response, usage = self._run(prompt)

        cost_usd = self.ledger.record(self.ROLE, seq, usage)
        state.cumulative_cost_usd += cost_usd

        conv_path = conv_log.save(
            role=self.ROLE, sequence=seq, iteration=state.iteration,
            task_description=task, content=response,
            ref_files=[f.name for f in sorted(
                (self.project_root / "conversation").glob("P1_*.md")
            )] if (self.project_root / "conversation").exists() else [],
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
