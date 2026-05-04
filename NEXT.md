# 다음 태스크 (MVP 완성 이후)

> 이 문서는 `스마트팩토리 시계열 데이터 처리 백엔드 MVP` 구현 완료 후 진행할 서브 프로젝트를 기록한다.
> MVP 진행 중에는 여기에 기술된 작업을 수행하지 않는다.

---

## Sub-Project: Orchestrator 독립 레포 추출

**목적**: 현재 `orchestrator/`를 별도 레포로 분리하여 다른 프로젝트에서도 재사용 가능한 범용 멀티 에이전트 파이프라인 도구로 만든다.

**선행 조건**: 스마트팩토리 MVP 완성 및 `main` 머지

**작업 순서**:

1. **프롬프트 분리**
   - `orchestrator/agents/planner.py`, `builder.py`의 하드코딩된 프롬프트를
     `prompts/planner_prompt.md`, `prompts/builder_prompt.md`로 추출
   - 각 agent가 해당 파일을 읽어 프롬프트를 구성하도록 수정

2. **`config.py` 범용화**
   - `PROJECT_ROOT`를 하드코딩 대신 CLI 인자(`--project-dir`)로 받도록 수정
   - 프로젝트별 `ESTIMATED` 추정치도 프로젝트 디렉토리 내 파일에서 읽도록 변경

3. **독립 레포 생성 및 추출**
   - 새 레포 생성 (예: `multi-agent-orchestrator`)
   - `orchestrator/` 코드를 새 레포로 이전
   - 실행 방식 변경: `python ~/multi-agent-orchestrator/main.py --project-dir .`

4. **timescale 레포 정리**
   - `orchestrator/` 디렉토리 제거 또는 git submodule로 대체
   - `prompts/` 디렉토리 신설 (프로젝트별 프롬프트만 남김)

**추출 후 각 레포의 역할**:

```
multi-agent-orchestrator/   ← 범용 오케스트레이터 (재사용 가능)
  agents/, parsing/, logging/, pipeline.py ...

timescale/                  ← 프로젝트별 설정만 보유
  AGENTS.md, role/*.md, spec.md, prompts/
```
