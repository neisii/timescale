# BUILDER Agent 지침

## 에이전트 설정

| 항목 | 값 |
|---|---|
| **AI Model** | Claude Sonnet 4.6 |
| **Effort Level** | Medium |

## 역할 정의

PLANNER의 설계 문서를 기반으로 실제 동작하는 코드를 작성한다.
Docker로 즉시 실행 가능한 수준의 완전한 코드를 제공해야 한다.

---

## 반드시 해야 할 것 (MUST DO)

### 구현 범위 준수
- PLANNER의 TODO 리스트 순서를 따라 구현한다.
- 다음 5개 컴포넌트를 모두 구현한다:
  1. **Producer**: IoT 센서 시뮬레이터 — 정상/이상/결측/노이즈/지연 데이터 생성
  2. **Kafka Producer/Consumer**: 메시지 발행 및 소비
  3. **Redis Dedup**: 고유 ID 기반 TTL 중복 제거 로직
  4. **DB 저장**: TimescaleDB 또는 PostgreSQL 시계열 데이터 영속화
  5. **FastAPI API**: 설비 상태 조회, 이상 이벤트 조회, 시간 범위 기반 조회 3개 엔드포인트

### 데이터 시나리오 구현
- Producer에서 다음 5가지 데이터 유형을 모두 생성해야 한다:
  - 정상 데이터: 설정된 범위 내 값
  - 이상 데이터: 급격한 spike 또는 drop
  - 결측 데이터: null 또는 누락 구간
  - 노이즈 데이터: 랜덤 변동 포함
  - 지연 데이터: 과거 timestamp를 가진 out-of-order 이벤트

### 이벤트 처리 순서 준수
Consumer는 반드시 다음 순서로 처리한다:
1. 이벤트 수신
2. 유효성 검증 (timestamp 유효성, 값 범위)
3. Redis 중복 확인
4. 시간 기준 필터링 (event time 기준)
5. DB 저장

### 시간 처리
- event time(`timestamp` 필드)과 processing time(현재 시각)을 코드 내에서 명확히 구분한다.
- time window 처리(1분 또는 10분)를 Consumer 로직에 반영한다.
- 지연 이벤트는 PLANNER가 정의한 정책에 따라 수용/거부 처리한다.

### 장애 처리
- Consumer 실패 시 재시작 가능하도록 offset을 적절히 커밋한다 (at-least-once).
- 처리 실패한 이벤트는 DLQ 또는 로그에 기록한다.
- Redis 연결 실패, DB 연결 실패 상황에 대한 기본 오류 처리를 포함한다.

### 인프라 구성

`docker-compose up` 한 명령으로 클론 후 즉시 실행 가능해야 한다. 사용자가 수동으로 설정해야 하는 항목이 있어서는 안 된다.

**필수 포함 서비스**
- Kafka (KRaft 모드 권장 — Zookeeper 의존성 제거)
- Redis
- TimescaleDB (`timescale/timescaledb` 이미지 사용, `postgres` 이미지 사용 금지)
- Producer, Consumer, API 서비스

**Kafka 리스너 설정 (반드시 준수)**

컨테이너 내부 통신용과 호스트 접근용 리스너를 반드시 분리한다. 아래 패턴을 따른다:
```yaml
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,PLAINTEXT_HOST://localhost:29092
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,PLAINTEXT_HOST://0.0.0.0:29092
```
Producer·Consumer 서비스는 컨테이너 내부 주소(`kafka:9092`)로 접속한다.

**서비스 기동 순서 제어**

`depends_on`만으로는 부족하다. 각 인프라 서비스에 `healthcheck`를 정의하고, 애플리케이션 서비스는 `condition: service_healthy`로 대기한다:
```yaml
depends_on:
  kafka:
    condition: service_healthy
  db:
    condition: service_healthy
  redis:
    condition: service_healthy
```
Producer·Consumer·API 서비스에는 `restart: on-failure`를 설정하여 인프라 준비 전 기동 실패 시 자동 재시도한다.

**각 서비스 healthcheck 기준**

| 서비스 | healthcheck 명령 |
|---|---|
| Kafka | `kafka-topics.sh --bootstrap-server localhost:9092 --list` |
| TimescaleDB | `pg_isready -U ${POSTGRES_USER}` |
| Redis | `redis-cli ping` |

**TimescaleDB 초기화**

`infra/init/` 디렉토리에 초기화 SQL 스크립트를 작성하고 docker-compose volume으로 마운트한다:
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS sensor_events (...);
SELECT create_hypertable('sensor_events', 'timestamp', if_not_exists => TRUE);
```
docker-compose의 `/docker-entrypoint-initdb.d/` 경로에 마운트하여 컨테이너 최초 기동 시 자동 실행되도록 한다.

**Kafka 토픽 자동 생성**

`infra/init/` 에 토픽 생성 스크립트를 작성하거나, docker-compose에 init 컨테이너를 추가하여 Kafka 기동 후 자동으로 토픽을 생성한다:
```yaml
kafka-init:
  image: confluentinc/cp-kafka:latest
  depends_on:
    kafka:
      condition: service_healthy
  command: kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists --topic sensor-events --partitions 3
```

**환경변수 관리**

- `.env.example` 파일을 작성하여 필요한 환경변수 목록과 기본값을 제공한다.
- `.env` 파일은 `.gitignore`에 추가한다.
- docker-compose는 `.env` 파일을 자동으로 읽으므로 사용자는 `.env.example`을 복사하여 즉시 사용할 수 있어야 한다.

**검증 스크립트**

`infra/verify.sh`를 작성하여 전체 스택이 정상 기동되었는지 자동으로 확인한다:
```bash
# 각 서비스 healthcheck 상태 확인
# Kafka 토픽 존재 여부 확인
# TimescaleDB hypertable 생성 여부 확인
# Redis ping 응답 확인
# API /health 엔드포인트 응답 확인
```

### 코드 품질
- 각 파일은 완전한 코드를 제공한다 (불완전한 스텁 금지).
- 중요한 로직(dedup, time window, 장애 처리)에는 간결한 주석을 남긴다.
- 파일 구조는 PLANNER가 정의한 디렉토리 구조를 따른다.

### openapi.yml 생성
- FastAPI 앱 구동 후 `/openapi.json` 엔드포인트를 export하거나 `app.openapi()`를 호출하여 `api/openapi.yml`로 저장한다.
- 추가 구현 없이 FastAPI가 자동 생성하므로 반드시 포함한다.
- 각 엔드포인트에 `summary`, `description`, `response_model`이 명시되어 있어야 스펙이 의미 있게 생성된다.

### plan.md 갱신
- PLANNER가 작성한 `plan.md`의 "Phase 분할 및 진행 현황" 표에서 **Phase 2(BUILDER) 상태를 완료로 갱신**한다.
- 구현 과정에서 PLANNER 설계와 달라진 결정이 있으면 "기술 결정 요약"과 "다음 Agent에게" 항목도 업데이트한다.

### 이력 기록 (Operation & Logging)
- 작업 시작 전 `conversation/P1_*` 문서를 모두 확인하여 PLANNER의 설계 의도를 파악한다.
- 구현을 완료한 후, 반드시 `conversation/` 디렉토리에 이력 문서를 기록한다.
- 파일명 규칙: `P2_{순번}_{Task명}_BUILDER.md`
  - 예: `conversation/P2_01_Initial-Implementation_BUILDER.md`
- 이력 문서에는 다음을 포함한다:
  - 참조한 PLANNER 문서 번호 (예: `참조: P1_01_Architecture-Design_PLANNER.md`)
  - 구현된 파일 목록 및 각 파일의 핵심 로직 설명
  - PLANNER 설계와 다르게 구현한 부분 및 이유

### 비용 기록 (Cost Logging)
- 이력 문서 작성 후, `cost/` 디렉토리에 비용 기록 문서를 **반드시 별도로** 작성한다.
- 파일명: `cost/P2_{순번}_{Task명}_BUILDER_cost.md`
  - 예: `cost/P2_01_Initial-Implementation_BUILDER_cost.md`
- API 응답의 `usage` 필드에서 `input_tokens`, `output_tokens`, `cache_read_input_tokens`를 확인하여 기록한다.
- 기록 형식은 `AGENTS.md` [섹션 10-6]의 템플릿을 따른다.

> **제출 전 체크**:
> - `conversation/P2_XX_..._BUILDER.md` 파일을 작성했는가?
> - `cost/P2_XX_..._BUILDER_cost.md` 파일을 작성했는가?

---

## 절대 하지 말아야 할 것 (MUST NOT DO)

- **AI/ML 모델을 구현하지 않는다.** 이상 감지 알고리즘, 예측 모델 등을 추가하지 않는다.
- **spec.md에 없는 기능을 임의로 추가하지 않는다.** 인증, 권한 관리, 대시보드 등 과도한 기능을 구현하지 않는다.
- **PLANNER 설계를 무단으로 변경하지 않는다.** 설계와 다르게 구현해야 할 경우 반드시 Notes에 이유를 명시한다.
- **처리 순서를 바꾸지 않는다.** 유효성 검증 전에 저장하거나, 중복 확인 전에 처리하는 등의 순서 위반을 하지 않는다.
- **미완성 코드를 제출하지 않는다.** `TODO`, `pass`, `...`, `NotImplemented` 등 구현되지 않은 부분을 남기지 않는다.
- **`postgres` 이미지를 TimescaleDB 용도로 사용하지 않는다.** 반드시 `timescale/timescaledb` 이미지를 사용한다.
- **`depends_on`만으로 기동 순서를 제어하지 않는다.** 반드시 `condition: service_healthy`와 healthcheck를 함께 사용한다.
- **Kafka 리스너를 단일로 설정하지 않는다.** 컨테이너 내부·외부 리스너를 반드시 분리한다.
- **`.env` 파일을 레포에 커밋하지 않는다.** `.env.example`만 커밋한다.
- **Kafka 토픽과 TimescaleDB hypertable을 수동 생성에 의존하지 않는다.** 반드시 자동 초기화 스크립트로 처리한다.
- **event time과 processing time을 혼용하지 않는다.** 시간 기준 필터링은 반드시 event time 기준으로 수행한다.
- **Redis dedup을 생략하지 않는다.** 성능 이유로 dedup 로직을 건너뛰지 않는다.

---

## 출력 형식

```
[Code]
- 파일 경로와 완전한 코드 내용

[Notes]
- 중요한 로직 설명
- PLANNER 설계와 다르게 구현한 부분 및 이유
```
