"""FIXER agent — escalating config per issue category (A → Haiku, B/C → Sonnet+thinking)."""

from pathlib import Path

from agents.base import BaseAgent
from config import FIXER_ESCALATION, PROJECT_ROOT
from state import PipelineState, AgentResult
from ledger import TokenLedger
from parsing.models import ReviewResult, FixerDecision
import agent_io.conversation as conv_log
import agent_io.cost as cost_log


class FixerAgent(BaseAgent):
    ROLE = "fixer"

    def __init__(self, ledger: TokenLedger, project_root: Path = PROJECT_ROOT):
        super().__init__(project_root)
        self.ledger = ledger

    # ── Model / config selection ───────────────────────────────────────────────

    def _select_config(self, review_result: ReviewResult, state: PipelineState) -> FixerDecision:
        category = review_result.dominant_category
        area_key = f"iter{state.iteration}_cat{category}"
        record   = state.get_escalation(category, area_key)

        tiers    = FIXER_ESCALATION.get(category, FIXER_ESCALATION["B"])
        tier_idx = min(record.current_tier, len(tiers) - 1)

        return FixerDecision(
            config=tiers[tier_idx],
            category=category,
            escalation_tier=record.current_tier,
            escalated=record.current_tier > 0,
        )

    def _record_result(
        self,
        decision: FixerDecision,
        success: bool,
        state: PipelineState,
    ) -> bool:
        """
        Update escalation tracker. Returns True when all tiers exhausted
        (PLANNER re-escalation needed).
        """
        area_key = f"iter{state.iteration}_cat{decision.category}"
        record   = state.get_escalation(decision.category, area_key)
        tiers    = FIXER_ESCALATION.get(decision.category, FIXER_ESCALATION["B"])

        record.model_history.append((decision.model, decision.thinking))

        if success:
            record.fail_count = 0
        else:
            record.fail_count += 1
            if record.fail_count >= 2:
                record.current_tier += 1
                record.fail_count    = 0
                if record.current_tier >= len(tiers):
                    return True  # all tiers exhausted

        return False

    # ── Run ────────────────────────────────────────────────────────────────────

    def run(
        self,
        state: PipelineState,
        review_result: ReviewResult,
    ) -> tuple[AgentResult, bool]:
        """Execute FIXER. Returns (AgentResult, planner_escalation_needed)."""
        task     = f"Fix-Iteration{state.iteration}"
        seq      = state.next_sequence(self.ROLE)
        decision = self._select_config(review_result, state)

        context      = self._build_context(state.iteration)
        issues_text  = self._format_issues(review_result)
        escalation_note = (
            f"\n> ⚠️  Escalation: tier {decision.escalation_tier} "
            f"(model={decision.model}, thinking={decision.thinking})\n"
            if decision.escalated else ""
        )

        prompt = f"""{context}

---
{escalation_note}
## REVIEWER가 식별한 이슈

{issues_text}

---

당신은 FIXER입니다. 위 이슈들을 최소한의 변경으로 수정하십시오.

- High severity 이슈를 최우선으로 처리하십시오.
- 전체 시스템을 재작성하지 마십시오. 영향받는 파일의 해당 부분만 수정하십시오.
- 수정 후 docker-compose 환경에서 실행 가능한지 자가 검증하십시오.
- AGENTS.md [섹션 10]에 정의된 출력 형식을 따르십시오.
"""

        print(
            f"\n[P4] FIXER — {seq} (iteration {state.iteration})"
            f"  model={decision.model}  thinking={decision.thinking}"
        )
        response, usage = self._run(prompt, config=decision.config)

        success = "[Fix Summary]" in response or "수정 완료" in response
        planner_needed = self._record_result(decision, success, state)

        cost_usd = self.ledger.record(self.ROLE, seq, usage)
        state.cumulative_cost_usd += cost_usd

        escalation_log = (
            f"\n## Escalation Log\n"
            f"- Tier: {decision.escalation_tier}\n"
            f"- Model: {decision.model}  thinking: {decision.thinking}\n"
            if decision.escalated else ""
        )

        ref_files = sorted(
            (self.project_root / "conversation").glob("P3_*.md")
        ) if (self.project_root / "conversation").exists() else []

        conv_path = conv_log.save(
            role=self.ROLE, sequence=seq, iteration=state.iteration,
            task_description=task,
            content=response + escalation_log,
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
        print(f"    → {conv_path.name}  (${cost_usd:.4f})  escalate_to_planner={planner_needed}")
        return agent_result, planner_needed

    def _format_issues(self, review_result: ReviewResult) -> str:
        if review_result.parse_error:
            return review_result.raw_text[:3000]
        lines = []
        for i, issue in enumerate(review_result.high_issues, 1):
            lines.append(
                f"{i}. {issue.description}\n"
                f"   - Severity: {issue.severity}  Category: {issue.category}\n"
                f"   - Files: {', '.join(issue.affected_files) or '(미지정)'}"
            )
        return "\n\n".join(lines) if lines else "(High 이슈 없음)"
