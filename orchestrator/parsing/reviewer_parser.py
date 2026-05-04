"""Parse REVIEWER markdown output into structured ReviewResult."""

import re
from parsing.models import Issue, ReviewResult

# ── Section extraction ─────────────────────────────────────────────────────────

_SECTION_RE = re.compile(
    r'\[Issues\](.*?)(?=\n\[|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# ── Per-issue field extraction ─────────────────────────────────────────────────

_SEVERITY_RE = re.compile(r'[-*]?\s*Severity\s*:\s*(high|medium|low)', re.IGNORECASE)
_CATEGORY_RE = re.compile(r'[-*]?\s*Category\s*:\s*([ABC])', re.IGNORECASE)
_FILE_RE     = re.compile(r'`([^`]+\.[a-z]+)`')

# Fallback: bare "high" near issue markers even without structured fields
_FALLBACK_HIGH_RE = re.compile(r'(high\s*severity|severity[:\s]+high)', re.IGNORECASE)


def parse(text: str) -> ReviewResult:
    """
    Parse REVIEWER output text → ReviewResult.

    Strategy:
    1. Extract [Issues] section.
    2. Split into individual issue blocks (each starts with a description line).
    3. For each block, extract Severity and Category via regex.
    4. If structured parsing yields 0 issues, fall back to keyword scan.
    """
    section_match = _SECTION_RE.search(text)
    if not section_match:
        return _fallback(text)

    section = section_match.group(1).strip()
    if not section:
        return ReviewResult(raw_text=text)

    issues = _parse_issue_blocks(section)
    if not issues:
        return _fallback(text)

    return ReviewResult(issues=issues, raw_text=text)


def _parse_issue_blocks(section: str) -> list:
    """
    Split section into blocks by detecting description lines (start with '- ' or a number).
    Each block ends when the next description starts.
    """
    # Split on lines that look like issue starters: "- Some description" or "1. ..."
    block_re = re.compile(r'(?:^|\n)(?:-\s+|\d+\.\s+)(?!Severity|Category|Affected)', re.MULTILINE)
    positions = [m.start() for m in block_re.finditer(section)]

    if not positions:
        # Try treating the whole section as one block
        return _extract_issue(section)

    blocks = []
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(section)
        block = section[start:end].strip()
        extracted = _extract_issue(block)
        blocks.extend(extracted)

    return blocks


def _extract_issue(block: str) -> list:
    """Extract 0 or 1 Issue from a text block."""
    sev_match = _SEVERITY_RE.search(block)
    cat_match = _CATEGORY_RE.search(block)

    if not sev_match:
        return []

    severity = sev_match.group(1).lower()
    category = cat_match.group(1).upper() if cat_match else "B"  # default to B if missing

    # Description: first non-empty line of the block
    first_line = next(
        (ln.lstrip("-* \t") for ln in block.splitlines() if ln.strip()
         and not _SEVERITY_RE.search(ln) and not _CATEGORY_RE.search(ln)),
        block[:80],
    )

    files = _FILE_RE.findall(block)

    return [Issue(
        description=first_line.strip(),
        severity=severity,
        category=category,
        affected_files=files,
    )]


def _fallback(text: str) -> ReviewResult:
    """
    Conservative fallback: if [Issues] section not found or parse failed,
    scan whole text for high-severity signals.
    """
    has_high = bool(_FALLBACK_HIGH_RE.search(text))
    # Create a synthetic high issue so FIXER is triggered
    issues = []
    if has_high:
        issues.append(Issue(
            description="[파싱 실패] REVIEWER 출력에서 high severity 신호 감지됨 — 전체 텍스트 검토 필요",
            severity="high",
            category="B",
        ))
    return ReviewResult(issues=issues, raw_text=text, parse_error=True)
