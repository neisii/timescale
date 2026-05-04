# 다음 태스크 (MVP 완성 이후)

> 이 문서는 `스마트팩토리 시계열 데이터 처리 백엔드 MVP` 구현 완료 후 진행할 서브 프로젝트를 기록한다.
> MVP 진행 중에는 여기에 기술된 작업을 수행하지 않는다.

---

## Sub-Project: 범용 멀티 에이전트 오케스트레이터

### 목적

현재 `orchestrator/`는 스마트팩토리 프로젝트에 종속되어 있다. `AGENTS.md`와 `role/*.md`에 기술 스택, 이벤트 스키마, 디렉토리 구조 등 도메인 지식이 하드코딩되어 있어 다른 프로젝트에서 재사용하려면 이 파일들을 처음부터 다시 작성해야 한다.

이 서브 프로젝트의 목표는 오케스트레이터를 어떤 프로젝트에도 적용할 수 있는 범용 도구로 분리하는 것이다. 단, `AGENTS.md`와 `role/*.md`를 `spec.md`로부터 동적으로 생성하는 방식은 채택하지 않는다. 오케스트레이션 로직(에이전트 순서, iteration 규칙, 로깅 규칙 등)은 도메인과 무관한 재사용 가능한 지식이며 신중하게 작성된 템플릿으로 관리한다.

**선행 조건**: 스마트팩토리 MVP 완성 및 `main` 머지

---

### 핵심 설계 원칙

**분리 기준**: `AGENTS.md`의 내용을 두 종류로 구분한다.

| 재사용 가능 (오케스트레이터에 귀속) | 프로젝트마다 달라짐 (프로젝트 레포에 귀속) |
|---|---|
| 에이전트 구조 및 순서 | 기술 스택 |
| Iteration 규칙 | 이벤트/데이터 스키마 |
| 설계 원칙 | 데이터 시나리오 |
| 로깅·비용 기록 규칙 | 디렉토리 구조 |
| Git workflow | 구현 범위 |
| 공통 금지사항 | |

**bootstrapping**: 새 프로젝트 시작 시 `spec.md`를 직접 읽어 변수를 추출하고 템플릿에 주입해 `AGENTS.md`를 생성하는 단계를 제공한다. 생성된 파일은 사람이 검토·수정 후 사용한다.

---

### 작업 단계

#### Phase 1 — AGENTS.md 템플릿화

`AGENTS.md`에서 프로젝트 종속 섹션을 변수 플레이스홀더로 교체한 `AGENTS.template.md`를 작성한다.

```
AGENTS.template.md 변수 목록:
  {{PROJECT_NAME}}       프로젝트명
  {{TECH_STACK}}         기술 스택 목록
  {{ARCHITECTURE}}       핵심 아키텍처 흐름 (예: A → B → C → D)
  {{DATA_SCHEMA}}        이벤트/데이터 스키마 (JSON 예시 포함)
  {{DATA_SCENARIOS}}     처리해야 할 데이터 시나리오 목록
  {{DIRECTORY_STRUCTURE}} 디렉토리 구조
  {{SCOPE_INCLUDE}}      구현 범위 — 포함 항목
  {{SCOPE_EXCLUDE}}      구현 범위 — 제외 항목
```

나머지 섹션(에이전트 구조, iteration 규칙, 로깅, git, 설계 원칙, 금지사항)은 고정값으로 템플릿에 포함한다.

`role/PLANNER.template.md`, `role/BUILDER.template.md` 등도 동일하게 작성한다. 각 role 파일에서 도메인 특화 지침(Kafka 파티션 전략, Redis dedup 등)을 제거하고 일반화된 지침으로 교체한다.

#### Phase 2 — Bootstrap 도구 작성

`bootstrap.py`를 작성한다. 이 스크립트는:

1. `spec.md`를 읽어 LLM(Haiku)으로 변수값을 추출한다.
2. 추출한 변수를 `AGENTS.template.md`와 `role/*.template.md`에 주입한다.
3. 결과물을 프로젝트 디렉토리에 `AGENTS.md`, `role/*.md`로 저장한다.
4. 사람이 검토할 수 있도록 변수 추출 결과를 별도 파일(`bootstrap_preview.md`)로 출력한다.

```
사용법:
  python bootstrap.py --spec ./spec.md --output-dir .
```

생성된 파일은 파이프라인 실행 전 사람이 반드시 검토한다. bootstrap은 초안 생성 도구이지 자동화 완성 도구가 아니다.

#### Phase 3 — 오케스트레이터 코드 범용화

`config.py`와 `main.py`를 수정해 프로젝트 경로를 인자로 받도록 변경한다.

- `PROJECT_ROOT`: `--project-dir` CLI 인자로 대체
- `ESTIMATED` 토큰 추정치: 프로젝트 디렉토리 내 `cost/cost-estimation.md`에서 읽도록 변경 (현재 동일)
- `AGENTS_MD`, `ROLE_FILES`, `SPEC_MD`: `--project-dir` 기준 상대 경로로 해석

#### Phase 4 — 독립 레포 추출

```
multi-agent-orchestrator/     ← 범용 엔진 (재사용 가능)
  agents/
  agent_io/
  parsing/
  pipeline.py
  config.py
  main.py
  bootstrap.py
  AGENTS.template.md
  role/
    PLANNER.template.md
    BUILDER.template.md
    REVIEWER.template.md
    FIXER.template.md

timescale/                    ← 프로젝트별 설정만 보유
  spec.md
  AGENTS.md          (bootstrap으로 생성 후 검토·확정)
  role/*.md          (bootstrap으로 생성 후 검토·확정)
```

실행 방식:

```bash
# 새 프로젝트 초기화
python ~/multi-agent-orchestrator/bootstrap.py --spec ./spec.md --output-dir .

# 파이프라인 실행
python ~/multi-agent-orchestrator/main.py --project-dir .
```

---

### 이 설계가 spec.md 기반 동적 생성과 다른 점

`AGENTS.md`와 `role/*.md`를 `spec.md`로부터 완전 자동 생성하는 방식은 채택하지 않는다. 이유:

- 오케스트레이션 로직(에이전트 순서, escalation 티어, 로깅 규칙)은 도메인과 무관하며 동적 생성 대상이 아니다.
- 자동 생성된 지침은 수작업으로 다듬은 지침보다 정밀도가 낮다.
- `spec.md`에서 지침을 도출하는 meta-agent 자체가 또 다른 고정 지침을 필요로 한다.

`bootstrap.py`는 **변수값만** 추출한다. 지침의 구조와 내용은 템플릿에서 관리한다.
