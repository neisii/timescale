"""Auto-generate cost/P{N}_{seq}_{task}_{ROLE}_cost.md after each agent run."""

from datetime import datetime
from pathlib import Path
from config import COST_DIR, PRICE_PER_MTOK, ESTIMATED
from state import UsageInfo


def save(
    role: str,
    sequence: str,
    iteration: int,
    task_description: str,
    usage: UsageInfo,
    cost_usd: float,
    cumulative_usd: float,
) -> Path:
    """
    Write a cost record file following the AGENTS.md §10-6 template.

    Returns the path of the created file.
    """
    COST_DIR.mkdir(parents=True, exist_ok=True)

    slug = task_description.replace(" ", "-").replace("/", "-")[:40]
    filename = f"{sequence}_{slug}_{role.upper()}_cost.md"
    path = COST_DIR / filename

    price = PRICE_PER_MTOK.get(usage.model, list(PRICE_PER_MTOK.values())[0])
    input_cost  = usage.input_tokens       * price["input"]  / 1_000_000
    output_cost = usage.output_tokens      * price["output"] / 1_000_000
    cache_cost  = usage.cache_read_tokens  * price["cache"]  / 1_000_000

    # drift vs estimation
    est = ESTIMATED.get(role, {})
    est_in  = est.get("input", 0)
    est_out = est.get("output", 0)
    drift_in  = f"{(usage.input_tokens  - est_in)  / est_in  * 100:+.1f}%" if est_in  else "—"
    drift_out = f"{(usage.output_tokens - est_out) / est_out * 100:+.1f}%" if est_out else "—"
    est_cost  = (
        est_in  * price["input"]  / 1_000_000
        + est_out * price["output"] / 1_000_000
    )
    drift_cost = f"{(cost_usd - est_cost) / est_cost * 100:+.1f}%" if est_cost else "—"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    content = f"""# {filename}

- **작성 Agent:** {role.upper()}
- **사용 모델:** {usage.model}
- **Iteration:** {iteration}
- **작성일시:** {timestamp}

---

## 사용량

| 항목 | 값 |
|---|---|
| 입력 토큰 | {usage.input_tokens:,} tokens |
| 출력 토큰 | {usage.output_tokens:,} tokens |
| 캐시 히트 토큰 | {usage.cache_read_tokens:,} tokens |
| 합계 토큰 | {usage.total_tokens:,} tokens |

## 비용

| 항목 | 계산식 | 금액 |
|---|---|---|
| 입력 비용 | {usage.input_tokens:,} × ${price['input']}/MTok | ${input_cost:.6f} |
| 출력 비용 | {usage.output_tokens:,} × ${price['output']}/MTok | ${output_cost:.6f} |
| 캐시 히트 비용 | {usage.cache_read_tokens:,} × ${price['cache']}/MTok | ${cache_cost:.6f} |
| **이 Task 합계** | | **${cost_usd:.6f}** |
| **누적 합계** | | **${cumulative_usd:.6f}** |

## 추정 대비 실측

| 항목 | 추정 (cost-estimation.md) | 실측 | 오차 |
|---|---|---|---|
| 입력 토큰 | {est_in:,} | {usage.input_tokens:,} | {drift_in} |
| 출력 토큰 | {est_out:,} | {usage.output_tokens:,} | {drift_out} |
| 비용 | ${est_cost:.6f} | ${cost_usd:.6f} | {drift_cost} |
"""
    path.write_text(content, encoding="utf-8")
    return path
