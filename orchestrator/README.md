# Orchestrator — Multi-Agent Pipeline

스마트팩토리 시계열 데이터 처리 백엔드 MVP를 자동 구현하는 Python 오케스트레이터.

```
python orchestrator/main.py [--iterations N] [--skip-git]
```

---

## 디렉토리 구조

```
orchestrator/
│
├── main.py                   진입점 (CLI 파싱 → Pipeline 실행)
├── pipeline.py               파이프라인 엔진 (단계 순서 제어, 루프 종료 판단)
├── config.py                 모델 ID, 단가, 경로, Escalation 티어 상수
├── state.py                  PipelineState (산출물, 반복 횟수, Escalation 추적)
├── ledger.py                 토큰·비용 집계 및 추정 대비 실측 drift 리포트
├── git_ops.py                브랜치 생성·커밋 자동화 (feat/* → phase/*)
├── requirements.txt          의존성 없음 (stdlib + claude CLI)
│
├── agents/
│   ├── base.py               BaseAgent: claude CLI subprocess, system prompt 주입
│   ├── planner.py            PLANNER  — Claude Opus 4.7
│   ├── builder.py            BUILDER  — Claude Sonnet 4.6
│   ├── reviewer.py           REVIEWER — Claude Sonnet 4.6
│   └── fixer.py              FIXER    — Haiku 4.5 (Cat.A) / Sonnet 4.6 (Cat.B/C)
│
├── parsing/
│   ├── models.py             Issue, ReviewResult, FixerDecision 데이터클래스
│   └── reviewer_parser.py    REVIEWER 출력 → Severity/Category 구조화 파싱
│
└── logging/
    ├── conversation.py       conversation/P{N}_{seq}_{task}_{ROLE}.md 자동 저장
    └── cost.py               cost/P{N}_{seq}_{task}_{ROLE}_cost.md 자동 저장
```

---

## 실제 작동 흐름

```
python orchestrator/main.py
         │
         ▼
    ┌─────────────────────────────────────────────────────────────┐
    │  Pipeline.__init__()                                        │
    │  TokenLedger, GitOps, PipelineState 초기화                  │
    │  PlannerAgent / BuilderAgent / ReviewerAgent / FixerAgent   │
    └──────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
╔══════════════════════════════════════════════════════════════════╗
║  PHASE 1 — PLANNER  (claude-opus-4-7)                          ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  _load_system_prompt()                                           ║
║    AGENTS.md + role/PLANNER.md → system prompt                  ║
║                                                                  ║
║  _run(prompt)                                                    ║
║    claude --print --model claude-opus-4-7                        ║
║           --output-format stream-json                            ║
║           --append-system-prompt {system}                        ║
║    stdin ← spec.md 전문                                          ║
║    stdout → stream-json 파싱 → result + UsageInfo               ║
║                                                                  ║
║  산출물 저장                                                      ║
║    plan.md, docs/architecture.md, docs/data-flow.md ...         ║
║    conversation/P1_01_Architecture-Design_PLANNER.md            ║
║    cost/P1_01_Architecture-Design_PLANNER_cost.md               ║
║                                                                  ║
║  [git] feat/planner-architecture 브랜치 생성 → 커밋             ║
║        → merge → phase/planner                                   ║
╚══════════════════════════════════════════════════════════════════╝
                               │
                               ▼
╔══════════════════════════════════════════════════════════════════╗
║  PHASE 2 — BUILDER  (claude-sonnet-4-6)                        ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  _load_system_prompt()                                           ║
║    AGENTS.md + role/BUILDER.md → system prompt                  ║
║                                                                  ║
║  collect_context("builder", iteration=0)                         ║
║    conversation/P1_* 전체 읽기 → 컨텍스트 문자열               ║
║                                                                  ║
║  _run(context + prompt)                                          ║
║    claude --print --model claude-sonnet-4-6 ...                  ║
║                                                                  ║
║  산출물 저장                                                      ║
║    producer/, consumer/, api/, infra/ 전체 코드                 ║
║    infra/docker-compose.yml, infra/.env.example                  ║
║    infra/verify.sh, api/openapi.yml                              ║
║    plan.md (Phase 2 상태 갱신)                                   ║
║    conversation/P2_01_Initial-Implementation_BUILDER.md         ║
║    cost/P2_01_Initial-Implementation_BUILDER_cost.md            ║
║                                                                  ║
║  [git] feat/builder-implementation → phase/builder              ║
╚══════════════════════════════════════════════════════════════════╝
                               │
                               ▼
         ┌─────────────────────────────────────┐
         │  iteration = 1  (max 3)             │◄──────────────────┐
         └──────────────────┬──────────────────┘                   │
                            │                                       │
                            ▼                                       │
╔══════════════════════════════════════════════════════════════════╗ │
║  PHASE 3 — REVIEWER  (claude-sonnet-4-6)                       ║ │
╠══════════════════════════════════════════════════════════════════╣ │
║                                                                  ║ │
║  collect_context("reviewer", iteration)                          ║ │
║    P1_* + P2_* (+ P4_* from iteration 2) 읽기                   ║ │
║  _collect_code_files()                                           ║ │
║    producer/, consumer/, api/, infra/ 파일 목록 수집             ║ │
║                                                                  ║ │
║  _run(context + code_list + prompt)                              ║ │
║                                                                  ║ │
║  reviewer_parser.parse(response)                                 ║ │
║    [Issues] 섹션 추출                                            ║ │
║    Severity / Category 정규식 파싱                               ║ │
║    → ReviewResult(issues, has_high_issues, dominant_category)   ║ │
║                                                                  ║ │
║  conversation/P3_{iter}_Review-Iteration{N}_REVIEWER.md         ║ │
║  cost/P3_{iter}_Review-Iteration{N}_REVIEWER_cost.md            ║ │
║  [git] feat/reviewer-iter{N} → phase/iter-{N}                   ║ │
╚═══════════════════════════╦══════════════════════════════════════╝ │
                            │                                       │
              ┌─────────────┴─────────────┐                        │
              │ has_high_issues?          │                        │
              │                           │                        │
             NO                          YES                       │
              │                           │                        │
              ▼                           ▼                        │
    ┌──────────────────┐    ╔══════════════════════════════════╗   │
    │  파이프라인 완료  │    ║  PHASE 4 — FIXER               ║   │
    │  high_issues     │    ╠══════════════════════════════════╣   │
    │  remain = False  │    ║                                  ║   │
    └──────────────────┘    ║  _select_model(review, state)    ║   │
                            ║                                  ║   │
                            ║  dominant_category = A?          ║   │
                            ║    → claude-haiku-4-5            ║   │
                            ║  dominant_category = B or C?     ║   │
                            ║    → claude-sonnet-4-6 (low)     ║   │
                            ║                                  ║   │
                            ║  연속 2회 실패 시 Escalation:    ║   │
                            ║    Haiku → Sonnet Low            ║   │
                            ║         → Sonnet Normal          ║   │
                            ║         → PLANNER 이관 (중단)   ║   │
                            ║                                  ║   │
                            ║  _run(context + issues + prompt) ║   │
                            ║                                  ║   │
                            ║  conversation/P4_{iter}_*.md     ║   │
                            ║  cost/P4_{iter}_*_cost.md        ║   │
                            ║  [git] feat/fixer-iter{N}        ║   │
                            ║        → phase/iter-{N}          ║   │
                            ╚══════════════╦═══════════════════╝   │
                                           │                       │
                              ┌────────────┴────────────┐          │
                              │ planner_escalation?     │          │
                              │                         │          │
                             NO                        YES         │
                              │                         │          │
                              │                         ▼          │
                              │               ┌──────────────────┐ │
                              │               │  파이프라인 중단  │ │
                              │               │  수동 재설계 필요 │ │
                              │               └──────────────────┘ │
                              │                                     │
                              │   iteration < max_iterations?       │
                              └─────────────────────────────────────┘
                                        (iteration += 1)


╔══════════════════════════════════════════════════════════════════╗
║  PIPELINE COMPLETE — 최종 리포트                                ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  TokenLedger.summary_report()                                    ║
║    Agent별 입력/출력 토큰, 모델, 비용                           ║
║                                                                  ║
║  TokenLedger.drift_report()                                      ║
║    cost-estimation.md 추정치 대비 실측 오차 (%)                 ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## Agent 간 데이터 흐름

```
                   spec.md
                      │
                      ▼
              ┌───────────────┐
              │   PLANNER     │── plan.md ──────────────────────────────┐
              │  Opus 4.7     │── docs/*.md                             │
              └───────┬───────┘                                         │
                      │ conversation/P1_*                               │
                      ▼                                                  │
              ┌───────────────┐                                         │
              │   BUILDER     │── producer/ consumer/ api/ infra/       │
              │  Sonnet 4.6   │── openapi.yml, verify.sh                │
              └───────┬───────┘                                         │
                      │ conversation/P2_*                               │
                      ▼                                                  │
              ┌───────────────┐                                         │
          ┌──►│   REVIEWER    │── ReviewResult ──────────────────┐      │
          │   │  Sonnet 4.6   │   (issues, severity, category)   │      │
          │   └───────────────┘                                  │      │
          │         conversation/P3_*                            │      │
          │                                                      ▼      │
          │   ┌───────────────┐                          ┌──────────┐   │
          │   │    FIXER      │◄─── FixerDecision ───────│  Parser  │   │
          │   │ Haiku/Sonnet  │     (model, effort,      └──────────┘   │
          │   └───────┬───────┘      category, tier)                    │
          │           │                                                  │
          │    수정된 코드 파일들                                        │
          │           │ conversation/P4_*                               │
          └───────────┘                                                  │
         (next iteration)                                                │
                                                                         │
                    plan.md (Phase 상태 갱신) ◄───────────────────────────┘
```

---

## 모델·비용 구성

```
┌──────────────────────────────────────────────────────────┐
│  Agent       Model              Input      Output        │
├──────────────────────────────────────────────────────────┤
│  PLANNER     claude-opus-4-7    $5/MTok    $25/MTok      │
│  BUILDER     claude-sonnet-4-6  $3/MTok    $15/MTok      │
│  REVIEWER    claude-sonnet-4-6  $3/MTok    $15/MTok      │
│  FIXER Cat.A claude-haiku-4-5   $1/MTok    $5/MTok       │
│  FIXER Cat.B claude-sonnet-4-6  $3/MTok    $15/MTok      │
│  FIXER Cat.C claude-sonnet-4-6  $3/MTok    $15/MTok      │
└──────────────────────────────────────────────────────────┘

Escalation (FIXER 동일 영역 2회 연속 실패 시):
  Cat.A:  Haiku  →  Sonnet Low  →  Sonnet Normal  →  PLANNER 이관
  Cat.B/C: Sonnet Low  →  Sonnet Normal  →  PLANNER 이관
```

---

## Git 브랜치 자동화

```
init (지침 문서)
│
├── phase/planner
│   └── feat/planner-architecture  ← PLANNER 완료 시 자동 커밋·머지
│
├── phase/builder
│   └── feat/builder-implementation  ← BUILDER 완료 시
│
├── phase/iter-1
│   ├── feat/reviewer-iter1          ← REVIEWER iteration 1
│   └── feat/fixer-iter1             ← FIXER iteration 1
│
├── phase/iter-2
│   ├── feat/reviewer-iter2
│   └── feat/fixer-iter2
│
└── phase/iter-3  (최종)
    └── feat/reviewer-iter3
              │
              └──► main  (수동 PR·머지)
```
