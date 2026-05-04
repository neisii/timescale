"""Auto-generate conversation/P{N}_{seq}_{task}_{ROLE}.md after each agent run."""

from datetime import datetime
from pathlib import Path
from config import CONVERSATION_DIR


def save(
    role: str,
    sequence: str,
    iteration: int,
    task_description: str,
    content: str,
    ref_files: list[str] | None = None,
) -> Path:
    """
    Write a conversation history file.

    Returns the path of the created file.
    """
    CONVERSATION_DIR.mkdir(parents=True, exist_ok=True)

    slug = task_description.replace(" ", "-").replace("/", "-")[:40]
    filename = f"{sequence}_{slug}_{role.upper()}.md"
    path = CONVERSATION_DIR / filename

    ref_section = "\n".join(f"- {f}" for f in (ref_files or [])) or "없음"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    header = f"""# {filename}

- **작성 Agent:** {role.upper()}
- **Iteration:** {iteration}
- **작성일시:** {timestamp}
- **참조 문서:** {ref_section}

---

"""
    path.write_text(header + content, encoding="utf-8")
    return path


def collect_context(role: str, iteration: int, project_root: Path) -> str:
    """
    Read previous conversation/ files relevant to the given role and return
    their combined content as a context string to prepend to the user prompt.

    Reference rules (from AGENTS.md §10-4):
      BUILDER   → P1_*
      REVIEWER  → P1_* + P2_* (+ P4_* from iteration 2 onwards)
      FIXER     → P3_* (+ P4_* from iteration 2 onwards)
    """
    conv_dir = project_root / "conversation"
    if not conv_dir.exists():
        return ""

    prefixes: list[str] = []
    if role == "builder":
        prefixes = ["P1_"]
    elif role == "reviewer":
        prefixes = ["P1_", "P2_"]
        if iteration >= 2:
            prefixes.append("P4_")
    elif role == "fixer":
        prefixes = ["P3_"]
        if iteration >= 2:
            prefixes.append("P4_")

    files = sorted(conv_dir.glob("*.md"))
    selected = [
        f for f in files
        if any(f.name.startswith(p) for p in prefixes)
    ]

    if not selected:
        return ""

    parts = ["## 이전 단계 작업 이력 (맥락 참조)\n"]
    for f in selected:
        parts.append(f"### {f.name}\n")
        parts.append(f.read_text(encoding="utf-8"))
        parts.append("\n---\n")

    return "\n".join(parts)
