"""Pipeline execution engine: PLANNER → BUILDER → [REVIEWER → FIXER] × max_iterations."""

import time
from datetime import datetime
from pathlib import Path

from config import PROJECT_ROOT, MAX_ITERATIONS, COST_DIR, AGENT_CONFIGS, FIXER_ESCALATION
from state import PipelineState
from ledger import TokenLedger
from git_ops import GitOps
from agents.planner import PlannerAgent
from agents.builder import BuilderAgent
from agents.reviewer import ReviewerAgent
from agents.fixer import FixerAgent


class Pipeline:
    def __init__(
        self,
        project_root: Path = PROJECT_ROOT,
        max_iterations: int = MAX_ITERATIONS,
        skip_git: bool = False,
        planner_only: bool = False,
    ):
        self.project_root  = project_root
        self.max_iterations = max_iterations
        self.skip_git      = skip_git
        self.planner_only  = planner_only

        self.ledger   = TokenLedger()
        self.git      = GitOps(project_root)
        self.state    = PipelineState(project_root=project_root)

        self.planner  = PlannerAgent(self.ledger, project_root)
        self.builder  = BuilderAgent(self.ledger, project_root)
        self.reviewer = ReviewerAgent(self.ledger, project_root)
        self.fixer    = FixerAgent(self.ledger, project_root)

        self._pipeline_start: float = 0.0
        self._phase_timings: list[dict] = []

    # ── Main entry ─────────────────────────────────────────────────────────────

    def run(self) -> PipelineState:
        self._pipeline_start = time.time()
        self._print_header()

        # Phase 1 — PLANNER
        print("\n" + "═" * 60)
        print("  Phase 1: PLANNER")
        print("═" * 60)
        self._phase_start("PLANNER")
        self.planner.run(self.state)
        self._phase_end("PLANNER")
        if not self.skip_git:
            self.git.commit_planner()

        if self.planner_only:
            self._print_summary()
            self._save_run_log()
            return self.state

        # Phase 2 — BUILDER
        print("\n" + "═" * 60)
        print("  Phase 2: BUILDER")
        print("═" * 60)
        self._phase_start("BUILDER")
        self.builder.run(self.state)
        self._phase_end("BUILDER")
        if not self.skip_git:
            self.git.commit_builder()

        # Phase 3/4 — REVIEWER / FIXER loop
        for iteration in range(1, self.max_iterations + 1):
            self.state.iteration = iteration

            print("\n" + "═" * 60)
            print(f"  Phase 3: REVIEWER  (iteration {iteration}/{self.max_iterations})")
            print("═" * 60)
            self._phase_start(f"REVIEWER-{iteration}")
            _, review_result = self.reviewer.run(self.state)
            self._phase_end(f"REVIEWER-{iteration}")

            if not self.skip_git:
                self.git.commit_reviewer(iteration)

            if not review_result.has_high_issues:
                print(f"\n✓  High severity 이슈 없음 — 파이프라인 완료 (iteration {iteration})")
                self.state.high_issues_remain = False
                break

            if iteration == self.max_iterations:
                print(f"\n⚠  Max iterations ({self.max_iterations}) 도달 — 종료")
                break

            print("\n" + "═" * 60)
            print(f"  Phase 4: FIXER  (iteration {iteration}/{self.max_iterations})")
            print("═" * 60)
            self._phase_start(f"FIXER-{iteration}")
            _, planner_needed = self.fixer.run(self.state, review_result)
            self._phase_end(f"FIXER-{iteration}")

            if not self.skip_git:
                self.git.commit_fixer(iteration)

            if planner_needed:
                print("\n⚠  FIXER Escalation 한도 초과 — PLANNER 재이관 필요")
                break

        self._print_summary()
        self._save_run_log()
        return self.state

    # ── Timing helpers ─────────────────────────────────────────────────────────

    def _phase_start(self, phase: str) -> None:
        self._phase_timings.append({"phase": phase, "start": time.time(), "end": 0.0})

    def _phase_end(self, phase: str) -> None:
        for t in reversed(self._phase_timings):
            if t["phase"] == phase and t["end"] == 0.0:
                t["end"] = time.time()
                t["elapsed"] = t["end"] - t["start"]
                print(f"    ⏱  {phase} 소요: {_fmt(t['elapsed'])}")
                break

    # ── Reporting ──────────────────────────────────────────────────────────────

    def _print_header(self) -> None:
        p_cfg = AGENT_CONFIGS["planner"]
        b_cfg = AGENT_CONFIGS["builder"]
        r_cfg = AGENT_CONFIGS["reviewer"]
        f0    = FIXER_ESCALATION["A"][0]

        print("=" * 60)
        print("  스마트팩토리 시계열 백엔드 MVP — Multi-Agent Pipeline")
        print("=" * 60)
        print(f"  시작 시각      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Max iterations : {self.max_iterations}")
        print(f"  Git automation : {'off' if self.skip_git else 'on'}")
        print(f"  PLANNER        : {p_cfg['model']}  thinking={p_cfg['thinking']}")
        print(f"  BUILDER        : {b_cfg['model']}  thinking={b_cfg['thinking']}")
        print(f"  REVIEWER       : {r_cfg['model']}  thinking={r_cfg['thinking']}")
        print(f"  FIXER tier-0   : {f0['model']}  thinking={f0['thinking']}")
        print("=" * 60)

    def _print_summary(self) -> None:
        total = time.time() - self._pipeline_start
        print("\n" + "=" * 60)
        print("  PIPELINE COMPLETE")
        print("=" * 60)
        print(f"  종료 시각         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  총 소요 시간      : {_fmt(total)}")
        print(f"  Iterations        : {self.state.iteration}")
        print(f"  High issues remain: {self.state.high_issues_remain}")
        print(f"  Total cost (USD)  : ${self.state.cumulative_cost_usd:.4f}")
        print()
        print("  ── 단계별 소요 시간 ──────────────────────────────────")
        for t in self._phase_timings:
            bar = "█" * int(t["elapsed"] / total * 30)
            print(f"  {t['phase']:<20} {_fmt(t['elapsed']):>10}  {bar}")
        print()
        print(self.ledger.summary_report())
        print()
        print(self.ledger.drift_report())

    def _save_run_log(self) -> None:
        COST_DIR.mkdir(parents=True, exist_ok=True)

        start_dt  = datetime.fromtimestamp(self._pipeline_start)
        end_dt    = datetime.now()
        total_sec = (end_dt - start_dt).total_seconds()

        filename = f"run_{start_dt.strftime('%Y%m%d_%H%M%S')}.md"
        path     = COST_DIR / filename

        phase_rows = "\n".join(
            f"| {t['phase']:<22} | {datetime.fromtimestamp(t['start']).strftime('%H:%M:%S')} "
            f"| {datetime.fromtimestamp(t['end']).strftime('%H:%M:%S')} "
            f"| {_fmt(t['elapsed'])} |"
            for t in self._phase_timings
        )

        p_cfg = AGENT_CONFIGS["planner"]
        b_cfg = AGENT_CONFIGS["builder"]
        r_cfg = AGENT_CONFIGS["reviewer"]

        content = f"""# Pipeline Run Log — {start_dt.strftime('%Y-%m-%d %H:%M:%S')}

## 실행 요약

| 항목 | 값 |
|---|---|
| 시작 시각 | {start_dt.strftime('%Y-%m-%d %H:%M:%S')} |
| 종료 시각 | {end_dt.strftime('%Y-%m-%d %H:%M:%S')} |
| 총 소요 시간 | {_fmt(total_sec)} |
| Iterations | {self.state.iteration} |
| High issues remain | {self.state.high_issues_remain} |
| 총 비용 (USD) | ${self.state.cumulative_cost_usd:.6f} |
| Git automation | {'off' if self.skip_git else 'on'} |

## 모델 구성

| Agent | Model | Thinking |
|---|---|---|
| PLANNER | {p_cfg['model']} | {p_cfg['thinking']} |
| BUILDER | {b_cfg['model']} | {b_cfg['thinking']} |
| REVIEWER | {r_cfg['model']} | {r_cfg['thinking']} |
| FIXER | escalation 테이블 | — |

## 단계별 소요 시간

| Phase | 시작 | 종료 | 소요 시간 |
|---|---|---|---|
{phase_rows}

## 토큰 및 비용

{self.ledger.summary_report()}

## 추정 대비 실측

{self.ledger.drift_report()}
"""
        path.write_text(content, encoding="utf-8")
        print(f"\n  실행 로그 저장: cost/{filename}")


def _fmt(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"
