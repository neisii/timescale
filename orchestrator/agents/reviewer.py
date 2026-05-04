"""REVIEWER agent — Sonnet 4.6, no extended thinking."""

from pathlib import Path

from agents.base import BaseAgent
from config import PROJECT_ROOT
from state import PipelineState, AgentResult
from ledger import TokenLedger
from parsing.reviewer_parser import parse
from parsing.models import ReviewResult
import agent_io.conversation as conv_log
import agent_io.cost as cost_log


class ReviewerAgent(BaseAgent):
    ROLE = "reviewer"

    def __init__(self, ledger: TokenLedger, project_root: Path = PROJECT_ROOT):
        super().__init__(project_root)
        self.ledger = ledger

    def run(self, state: PipelineState) -> tuple[AgentResult, ReviewResult]:
        task = f"Review-Iteration{state.iteration}"
        seq  = state.next_sequence(self.ROLE)

        context      = self._build_context(state.iteration)
        code_summary = self._collect_code_files()

        prompt = f"""{context}

---

## 현재 코드베이스 파일 목록

{code_summary}

---

당신은 REVIEWER입니다. 위의 구현 결과를 비판적으로 검토하십시오.

9개 체크리스트 항목을 모두 검토하고, 각 이슈에 Severity(high/medium/low)와
Category(A/B/C)를 반드시 함께 표기하십시오.

특히 **항목 9 (Docker 즉시 실행 가능성)**을 반드시 검토하십시오:
- Kafka ADVERTISED_LISTENERS 내부/외부 분리 여부
- service_healthy condition 사용 여부
- TimescaleDB 이미지 및 hypertable 초기화 스크립트 존재 여부
- verify.sh 존재 여부

AGENTS.md [섹션 10]에 정의된 출력 형식을 따르십시오.
"""

        print(f"\n[P3] REVIEWER — {seq} (iteration {state.iteration}) 검토 시작")
        response, usage = self._run(prompt)

        review_result = parse(response)
        high_count    = len(review_result.high_issues)
        print(f"    → High issues: {high_count}, parse_error: {review_result.parse_error}")

        cost_usd = self.ledger.record(self.ROLE, seq, usage)
        state.cumulative_cost_usd += cost_usd

        ref_files = sorted(
            list((self.project_root / "conversation").glob("P1_*.md"))
            + list((self.project_root / "conversation").glob("P2_*.md"))
        ) if (self.project_root / "conversation").exists() else []

        conv_path = conv_log.save(
            role=self.ROLE, sequence=seq, iteration=state.iteration,
            task_description=task, content=response,
            ref_files=[f.name for f in ref_files],
        )
        cost_log.save(
            role=self.ROLE, sequence=seq, iteration=state.iteration,
            task_description=task, usage=usage,
            cost_usd=cost_usd, cumulative_usd=state.cumulative_cost_usd,
        )

        agent_result = AgentResult(
            role=self.ROLE, raw=response, usage=usage,
            sequence=seq, filename=conv_path.name,
        )
        state.record_output(self.ROLE, agent_result)
        print(f"    → {conv_path.name}  (${cost_usd:.4f})")
        return agent_result, review_result

    def _collect_code_files(self) -> str:
        dirs  = ["producer", "consumer", "api", "infra"]
        lines = []
        for d in dirs:
            target = self.project_root / d
            if target.exists():
                for f in sorted(target.rglob("*")):
                    if f.is_file():
                        lines.append(f"- {f.relative_to(self.project_root)}")
        return "\n".join(lines) if lines else "*(아직 코드 파일 없음)*"
