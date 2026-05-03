# AGENTS.md — 전체 Agent 공통 지침

모든 Agent는 역할별 지침(`role/*.md`)에 앞서 이 문서를 먼저 숙지하고 준수한다.
이 문서의 규칙은 어떤 역할, 어떤 iteration에서도 예외 없이 적용된다.

> **작업 제출 전 체크**: 결과물을 제출하기 전 다음 두 가지를 반드시 확인한다.
> 1. `conversation/` 폴더에 아래 [섹션 10]에 정의된 명명 규칙으로 이력 문서를 작성했는가?
> 2. `cost/` 폴더에 아래 [섹션 10-6]에 정의된 명명 규칙으로 비용 기록 문서를 작성했는가?

---

## 1. 프로젝트 개요

**프로젝트명:** 스마트팩토리 시계열 데이터 처리 백엔드 MVP

**최종 목표:** 산업용 IoT 센서 데이터를 안정적으로 수집·처리·저장·조회하는 운영 가능한 백엔드 시스템을 설계하고 구현한다.

**핵심 아키텍처:**
```
Producer → Kafka → Consumer → DB → API
```

**기술 스택:**
- Python (FastAPI)
- Apache Kafka
- Redis (중복 제거 전용)
- PostgreSQL 또는 TimescaleDB
- Docker (전체 시스템 실행 환경)

**사양 문서:** `spec.md` (모든 요구사항의 최종 기준)

---

## 2. Agent 시스템 구조

### 역할 및 순서

```
PLANNER → BUILDER → REVIEWER → FIXER → REVIEWER (반복)
```

| Agent | 파일 | 핵심 책임 |
|---|---|---|
| PLANNER | `role/PLANNER.md` | 사양 분석 및 시스템 설계 |
| BUILDER | `role/BUILDER.md` | 설계 기반 코드 구현 |
| REVIEWER | `role/REVIEWER.md` | 구현 결과 비판적 검토 |
| FIXER | `role/FIXER.md` | 식별된 문제 최소 수정 |

### Iteration 규칙
- 최대 반복 횟수: **3회**
- 종료 조건: **High severity 이슈가 없거나** 최대 반복 횟수 도달
- 각 Agent는 자신의 차례가 아닌 작업을 수행하지 않는다.

---

## 3. 구현 범위 (Scope)

### 반드시 포함해야 할 것
- 시계열 데이터 처리 (`timestamp` 기반 이벤트 흐름)
- Redis TTL 기반 이벤트 중복 제거 (Deduplication)
- Event time / Processing time 구분
- Time window 처리 (1분 또는 10분 단위)
- 지연 이벤트(out-of-order) 처리 정책
- 장애 처리 (Kafka 지연, Consumer 실패, 데이터 중복, 데이터 유실)
- at-least-once 전달 보장
- Docker Compose 기반 실행 환경

### 절대 포함하지 말아야 할 것
- AI/ML 모델 구현 (이상 감지 알고리즘 포함)
- 사용자 인증 및 권한 관리
- 프론트엔드 또는 대시보드
- spec.md에 명시되지 않은 기능 일체

---

## 4. 이벤트 스키마 (공통 기준)

모든 Agent는 다음 스키마를 기준으로 설계하고 구현한다.

```json
{
  "event_id":  "string (고유 식별자, dedup 키)",
  "sensor_id": "string (Kafka Partition Key)",
  "timestamp": "ISO 8601 (event time 기준)",
  "value":     "float",
  "status":    "normal | anomaly | missing | delayed"
}
```

---

## 5. 데이터 시나리오 (공통 기준)

Producer는 다음 5가지 시나리오를 모두 생성해야 하며, 이후 모든 Agent는 이를 전제로 설계·구현·검토한다.

| 시나리오 | 설명 |
|---|---|
| 정상 데이터 | 설정된 값 범위 내 일정한 패턴 |
| 이상 데이터 | 급격한 spike 또는 drop 발생 |
| 결측 데이터 | null 값 또는 누락 구간 |
| 노이즈 데이터 | 랜덤 변동 포함 |
| 지연 데이터 | 과거 timestamp를 가진 out-of-order 이벤트 |

---

## 6. 이벤트 처리 순서 (불변 원칙)

Consumer는 반드시 다음 순서를 지킨다. 어떤 이유로도 순서를 바꾸지 않는다.

```
1. 이벤트 수신
2. 유효성 검증 (timestamp 유효성, 값 범위)
3. Redis 중복 확인 (event_id 기반)
4. 시간 기준 필터링 (event time 기준)
5. DB 저장
```

---

## 7. 디렉토리 구조 (공통 기준)

```
/
├── producer/         # IoT 센서 시뮬레이터
├── consumer/         # Kafka Consumer, 처리 로직
├── api/              # FastAPI 엔드포인트
│   └── openapi.yml   # API 스펙 (FastAPI 자동 생성, BUILDER 산출물)
├── infra/            # docker-compose.yml, 환경 설정
├── docs/             # architecture.md, data-flow.md, tradeoff.md,
│                     # failure-case.md, kafka-design.md
├── conversation/     # Agent 작업 이력 (의사결정 로그)
├── cost/             # Phase·Task별 실제 사용량 기록
├── role/             # Agent별 역할 지침
│   ├── PLANNER.md
│   ├── BUILDER.md
│   ├── REVIEWER.md
│   └── FIXER.md
├── AGENTS.md         # 본 문서 (전체 공통 지침)
├── plan.md           # 구현 계획 요약 (PLANNER 산출물, 세션 간 연결용)
└── spec.md           # 최종 요구사항 기준 문서
```

---

## 8. 필수 문서 산출물

| 파일 | 생성 주체 | 내용 |
|---|---|---|
| `plan.md` | **PLANNER** | 구현 계획 요약 — Phase 분할, 기술 결정, 트레이드오프 (세션 간 연결용 진입점) |
| `docs/architecture.md` | BUILDER | 전체 시스템 구조, 컴포넌트 역할 |
| `docs/data-flow.md` | BUILDER | 이벤트 흐름, 처리 순서, 시간 기준 처리 |
| `docs/tradeoff.md` | BUILDER | 설계 선택 이유, 트레이드오프 분석 |
| `docs/failure-case.md` | BUILDER | 장애 시나리오 및 대응 전략 |
| `docs/kafka-design.md` | BUILDER | Partition 전략, Lag 대응, Consumer 구조 |
| `api/openapi.yml` | **BUILDER** | FastAPI 자동 생성 API 스펙 (`app.openapi()` 또는 `/openapi.json` export) |

---

## 9. 설계 결정 원칙

모든 Agent는 설계 및 구현 과정에서 다음 원칙을 따른다.

1. **명확성 우선**: 복잡한 구조보다 이해하기 쉬운 구조를 선택한다.
2. **최소 구현**: 요구사항을 충족하는 가장 단순한 방법을 택한다. 과도한 추상화를 하지 않는다.
3. **근거 명시**: 모든 설계 결정에는 "왜 이렇게 했는가"를 반드시 남긴다.
4. **실행 가능성**: 모든 산출물은 `docker-compose up` 한 명령으로 실행 가능해야 한다.
5. **데이터 흐름 중심**: 기능 추가보다 데이터 흐름의 정확성과 신뢰성을 우선한다.

---

## 10. Operation & Logging: 의사결정 이력 관리 지침

### 10-1. 이력 기록 의무

모든 Agent는 작업을 마칠 때 반드시 `conversation/` 디렉토리에 해당 작업의 결과물을 기록한다.
이력 문서 없이 결과물을 제출하는 것은 작업 미완료로 간주한다.

### 10-2. 파일 명명 규칙

```
P{Phase}_{Sequence}_{Description}_{ROLE}.md
```

| 필드 | 설명 | 예시 |
|---|---|---|
| `Phase` | Agent 단계 번호 (1=PLANNER, 2=BUILDER, 3=REVIEWER, 4=FIXER) | `1`, `2`, `3`, `4` |
| `Sequence` | 동일 Phase 내 문서 순번 (두 자리) | `01`, `02` |
| `Description` | 작업 내용을 나타내는 영문 케밥 케이스 | `Architecture-Design` |
| `ROLE` | 작성 Agent 역할명 (대문자) | `PLANNER` |

### 10-3. 역할별 명명 예시 및 기록 내용

**PLANNER**
```
conversation/P1_01_Architecture-Design_PLANNER.md
conversation/P1_02_Data-Flow-Design_PLANNER.md
```
- 전체 시스템 설계 결과 (Architecture, Components, Data Flow, File Structure, Key Decisions, TODO List)
- 주요 의사결정과 그 근거

**BUILDER**
```
conversation/P2_01_Initial-Implementation_BUILDER.md
```
- 구현된 코드 목록 및 핵심 로직 설명
- 참조한 PLANNER 문서 번호 명시 (예: `참조: P1_01, P1_02`)
- PLANNER 설계와 다르게 구현한 부분 및 이유

**REVIEWER**
```
conversation/P3_01_Review-Iteration1_REVIEWER.md
conversation/P3_02_Review-Iteration2_REVIEWER.md
```
- 8개 체크리스트 항목별 검토 결과
- 발견된 Issues, Severity, Affected Areas
- 참조한 BUILDER 문서 번호 명시

**FIXER**
```
conversation/P4_01_Fix-Iteration1_FIXER.md
conversation/P4_02_Fix-Iteration2_FIXER.md
```
- 수정한 이슈 목록 및 변경 내용
- 참조한 REVIEWER 문서 번호 명시
- 처리하지 못한 이슈 및 이유

### 10-4. 파일 참조 의무

새로운 작업을 시작하는 Agent는 반드시 `conversation/` 내의 이전 순번 문서들을 먼저 참조하여 맥락(Context)을 파악한 뒤 작업을 수행한다.

- BUILDER는 작업 전 `P1_*` 문서를 모두 확인한다.
- REVIEWER는 작업 전 `P2_*` 문서를 모두 확인한다.
- FIXER는 작업 전 `P3_*` 문서를 모두 확인한다.
- 2번째 iteration 이후의 REVIEWER는 `P4_*` 문서도 함께 확인한다.

### 10-5. 이력 문서 필수 헤더

모든 이력 문서는 다음 헤더로 시작한다:

```markdown
# {파일명}

- **작성 Agent:** {ROLE}
- **Iteration:** {번호}
- **작성일시:** {YYYY-MM-DD HH:MM}
- **참조 문서:** {참조한 conversation/ 파일 목록, 없으면 "없음"}

---
```

### 10-6. 비용 기록 의무 (Cost Logging)

모든 Agent는 작업을 마칠 때 `conversation/` 이력 문서와 **별도로** `cost/` 디렉토리에 해당 Phase·Task의 실제 사용량을 기록한다.
이 기록은 `cost/cost-estimation.md`의 사전 추정치와 실측값을 비교하기 위한 목적이다.

#### 파일 명명 규칙

```
cost/P{Phase}_{Sequence}_{Description}_{ROLE}_cost.md
```

예시:
```
cost/P1_01_Architecture-Design_PLANNER_cost.md
cost/P2_01_Initial-Implementation_BUILDER_cost.md
cost/P3_01_Review-Iteration1_REVIEWER_cost.md
cost/P4_01_Fix-Iteration1_FIXER_cost.md
```

#### 비용 기록 문서 필수 항목

```markdown
# {파일명}

- **작성 Agent:** {ROLE}
- **사용 모델:** {모델명}
- **Iteration:** {번호}
- **작성일시:** {YYYY-MM-DD HH:MM}

---

## 사용량

| 항목 | 값 |
|---|---|
| 입력 토큰 | {숫자} tokens |
| 출력 토큰 | {숫자} tokens |
| 캐시 히트 토큰 | {숫자} tokens (없으면 0) |
| 합계 토큰 | {숫자} tokens |

## 비용

| 항목 | 계산식 | 금액 |
|---|---|---|
| 입력 비용 | {입력 토큰} × ${단가}/MTok | ${금액} |
| 출력 비용 | {출력 토큰} × ${단가}/MTok | ${금액} |
| 캐시 히트 비용 | {캐시 토큰} × ${단가}/MTok | ${금액} |
| **이 Task 합계** | | **${합계}** |
| **누적 합계** | (이전 Task 합산) | **${누적}** |

## 추정 대비 실측

| 항목 | 추정 (cost-estimation.md) | 실측 | 오차 |
|---|---|---|---|
| 입력 토큰 | {추정값} | {실측값} | {±%} |
| 출력 토큰 | {추정값} | {실측값} | {±%} |
| 비용 | {추정값} | {실측값} | {±%} |
```

#### 단가 참조

| 모델 | 입력 | 캐시 히트 | 출력 |
|---|---|---|---|
| Claude Opus 4.7 | $5 / MTok | $0.50 / MTok | $25 / MTok |
| Claude Sonnet 4.6 | $3 / MTok | $0.30 / MTok | $15 / MTok |
| Claude Haiku 4.5 | $1 / MTok | $0.10 / MTok | $5 / MTok |

> 실제 토큰 수는 API 응답의 `usage` 필드(`input_tokens`, `output_tokens`, `cache_read_input_tokens`)에서 확인한다.

---

## 11. Git Workflow

### 11-1. 브랜치 전략

```
main
├── init                              ← 지침 문서 (AGENTS.md, role/*.md, spec.md 등)
├── phase/planner                     ← PLANNER 산출물 통합 브랜치
│   ├── feat/planner-architecture     ← 아키텍처 설계 Task
│   └── feat/planner-dataflow         ← 데이터 흐름 설계 Task
├── phase/builder                     ← BUILDER 산출물 통합 브랜치
│   └── feat/builder-implementation   ← 구현 Task
├── phase/iter-1                      ← REVIEWER + FIXER 1회차 통합 브랜치
│   ├── feat/reviewer-iter1           ← REVIEWER 검토 Task
│   └── feat/fixer-iter1              ← FIXER 수정 Task
├── phase/iter-2                      ← REVIEWER + FIXER 2회차 통합 브랜치
│   ├── feat/reviewer-iter2
│   └── feat/fixer-iter2
└── phase/iter-3                      ← REVIEWER + FIXER 3회차 통합 브랜치
    ├── feat/reviewer-iter3
    └── feat/fixer-iter3
```

**규칙**
- 모든 작업은 `feat/*` 브랜치에서 수행한다. `phase/*` 브랜치에 직접 커밋하지 않는다.
- `phase/*` 브랜치는 해당 Phase의 모든 `feat/*` PR이 머지된 후에만 다음 단계로 PR을 올린다.

---

### 11-2. 커밋 컨벤션 (Conventional Commits)

```
{type}({scope}): {subject}
```

| type | 사용 시점 |
|---|---|
| `feat` | 새 설계 문서, 새 코드 구현 |
| `fix` | FIXER의 버그 수정, 로직 수정 |
| `docs` | conversation/, cost/ 이력 문서 추가 |
| `refactor` | 기능 변경 없는 코드 구조 개선 |
| `chore` | 설정 파일, .env, docker-compose 수정 |

**scope**: 작업 대상 컴포넌트 (`planner`, `builder`, `reviewer`, `fixer`, `producer`, `consumer`, `api`, `infra`)

예시:
```
feat(planner): define full system architecture and kafka partition strategy
feat(builder): implement redis dedup with TTL and kafka consumer pipeline
fix(fixer): correct event time filtering order in consumer
docs(reviewer): add review report for iteration 1
docs(fixer): add cost log for fix iteration 1
chore(infra): update docker-compose with timescaledb healthcheck
```

**Subject 규칙**
- 영문 소문자로 시작, 마침표 없음
- 50자 이내
- 명령형 현재 시제 (add / fix / update, not added / fixed / updated)

---

### 11-3. PR 규칙

#### PR 흐름

| PR | from | to | 머지 조건 |
|---|---|---|---|
| Task 완료 | `feat/*` | `phase/*` | conversation/ + cost/ 문서 존재, 커밋 컨벤션 준수 |
| PLANNER 완료 | `phase/planner` | `phase/builder` | P1_* 문서 전체 존재 |
| BUILDER 완료 | `phase/builder` | `phase/iter-1` | P2_* 문서 존재, docker-compose 실행 가능 |
| Iteration 완료 | `phase/iter-N` | `phase/iter-(N+1)` | High severity 이슈 없음 또는 max iteration 도달 |
| 최종 완료 | `phase/iter-최종` | `main` | 모든 High 이슈 해결, 전체 문서 완비 |

#### PR 템플릿

```markdown
## Summary
- Agent: {ROLE}
- Phase: {P1 / P2 / P3 / P4}
- Iteration: {번호}

## 작업 내용
- {주요 변경사항 bullet}

## 산출물 체크리스트
- [ ] conversation/{파일명} 작성 완료
- [ ] cost/{파일명} 작성 완료
- [ ] 커밋 컨벤션 준수

## 추정 대비 실측 비용
- 입력 토큰: {실측} (추정 대비 {±%})
- 출력 토큰: {실측} (추정 대비 {±%})
- 비용: ${실측} (추정 대비 {±%})

## 다음 Agent에게
- {인수인계 사항}
```

---

### 11-4. 공통 금지 사항

- `main` 브랜치에 직접 커밋하지 않는다.
- `phase/*` 브랜치에 직접 커밋하지 않는다. 반드시 `feat/*`에서 PR을 통해 머지한다.
- PR 없이 브랜치를 머지하지 않는다.
- conversation/ 또는 cost/ 문서가 없는 상태로 PR을 올리지 않는다.
- force push를 사용하지 않는다.

---

## 12. 공통 금지 사항

역할에 관계없이 모든 Agent에게 적용된다.

- `spec.md`를 무시하거나 임의로 재해석하지 않는다.
- 존재하지 않는 컴포넌트나 기능을 있다고 가정(hallucination)하지 않는다.
- 이전 iteration의 산출물을 확인하지 않고 새로 작성하지 않는다.
- 자신의 역할 범위를 벗어난 작업을 수행하지 않는다.
- "나중에 구현", "TODO", "생략 가능" 등의 표현으로 필수 요구사항을 회피하지 않는다.
