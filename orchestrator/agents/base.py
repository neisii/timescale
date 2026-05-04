"""BaseAgent: Anthropic SDK wrapper with native tool execution and extended thinking."""

import time
from datetime import datetime
from pathlib import Path

import anthropic

from config import AGENT_CONFIGS, THINKING_BUDGETS, HAIKU, AGENTS_MD, ROLE_FILES, PROJECT_ROOT
from state import UsageInfo

_WRITE_FAIL_THRESHOLD = 2  # consecutive write_file failures before aborting

_client = anthropic.Anthropic()

# ── Tool definitions ───────────────────────────────────────────────────────────

_TOOLS = [
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a file at a path relative to the project root. "
            "Parent directories are created automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Relative file path from project root"},
                "content": {"type": "string", "description": "Complete file content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Return the content of a file relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path from project root"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_dir",
        "description": "List files and subdirectories at a path relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative directory path (default: '.')"},
            },
        },
    },
]

_MAX_TOOL_ROUNDS = 30   # safety cap: prevent runaway tool loops
_MAX_RETRIES     = 3
_RETRY_BASE_S    = 10


class BaseAgent:
    ROLE: str = ""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.project_root = project_root

    # ── System prompt ──────────────────────────────────────────────────────────

    def _load_system_prompt(self) -> str:
        agents_md = AGENTS_MD.read_text(encoding="utf-8")
        role_md   = ROLE_FILES[self.ROLE].read_text(encoding="utf-8")
        return f"{agents_md}\n\n---\n\n## 당신의 역할\n\n{role_md}"

    # ── Context ────────────────────────────────────────────────────────────────

    def _build_context(self, iteration: int) -> str:
        from agent_io.conversation import collect_context
        return collect_context(self.ROLE, iteration, self.project_root)

    # ── Tool execution ─────────────────────────────────────────────────────────

    def _execute_tool(self, call) -> str:
        try:
            if call.name == "write_file":
                rel  = call.input["path"].lstrip("/")
                path = self.project_root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(call.input["content"], encoding="utf-8")
                print(f"      ✎ {rel}", flush=True)
                return f"OK: wrote {rel} ({len(call.input['content'])} chars)"

            if call.name == "read_file":
                rel  = call.input["path"].lstrip("/")
                path = self.project_root / rel
                if not path.exists():
                    return f"ERROR: {rel} not found"
                return path.read_text(encoding="utf-8")

            if call.name == "list_dir":
                rel      = (call.input.get("path") or ".").lstrip("/") or "."
                dir_path = self.project_root / rel
                if not dir_path.exists():
                    return f"ERROR: {rel} not found"
                entries = sorted(dir_path.iterdir())
                return "\n".join(
                    f"{'[DIR] ' if e.is_dir() else '[FILE]'} {e.name}"
                    for e in entries
                )

            return f"ERROR: unknown tool '{call.name}'"
        except Exception as exc:
            return f"ERROR: {exc}"

    # ── API call with retry ────────────────────────────────────────────────────

    def _api_call(self, **kwargs):
        # messages.create() raises ValueError for max_tokens that may exceed 10 min.
        # stream() + get_final_message() returns the same Message object without the limit.
        last_err: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                with _client.messages.stream(**kwargs) as stream:
                    return stream.get_final_message()
            except anthropic.RateLimitError as exc:
                last_err = exc
                wait = _RETRY_BASE_S * attempt
                print(f"\n    ↻ rate-limit  retry {attempt}/{_MAX_RETRIES} ({wait}s)...", flush=True)
                time.sleep(wait)
            except anthropic.APIConnectionError as exc:
                last_err = exc
                print(f"\n    ↻ connection error  retry {attempt}/{_MAX_RETRIES} ({_RETRY_BASE_S}s)...", flush=True)
                time.sleep(_RETRY_BASE_S)
        raise last_err or RuntimeError("API call failed after all retries")

    # ── Emergency dump ─────────────────────────────────────────────────────────

    def _emergency_dump(self, text: str, thinking: str, exc: Exception) -> None:
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.project_root / f"emergency_dump_{self.ROLE}_{ts}.md"
        sections = [f"# Emergency Dump — {self.ROLE}\n\n**Error:** {exc}\n"]
        if thinking:
            sections.append(f"## Thinking\n\n{thinking}")
        if text:
            sections.append(f"## Output\n\n{text}")
        if not thinking and not text:
            sections.append("*(no content captured)*")
        path.write_text("\n\n".join(sections), encoding="utf-8")
        print(f"\n    ⚠  emergency dump → {path.name}", flush=True)

    # ── Main run ───────────────────────────────────────────────────────────────

    def _run(self, prompt: str, config: dict | None = None) -> tuple[str, UsageInfo]:
        """
        Invoke Claude via Anthropic SDK with an agentic tool loop.

        Runs until stop_reason == 'end_turn' or no tool_use blocks remain.
        Extended thinking is enabled when config["thinking"] is set (Sonnet only).
        Returns (response_text, UsageInfo).
        """
        cfg          = config or AGENT_CONFIGS[self.ROLE]
        model        = cfg["model"]
        max_tokens   = cfg["max_tokens"]
        thinking_lvl = cfg.get("thinking")

        thinking_param: dict = {}
        if thinking_lvl and model != HAIKU:
            thinking_param = {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": THINKING_BUDGETS[thinking_lvl],
                }
            }

        label = f"[{model}"
        if thinking_lvl and model != HAIKU:
            label += f"  thinking={thinking_lvl}"
        label += "]"
        print(f"    {label} ", end="", flush=True)

        messages: list[dict] = [{"role": "user", "content": prompt}]
        usage           = UsageInfo(model=model)
        final_text      = ""
        final_thinking  = ""
        write_fail_streak = 0

        try:
            for _ in range(_MAX_TOOL_ROUNDS):
                resp = self._api_call(
                    model=model,
                    max_tokens=max_tokens,
                    system=self._load_system_prompt(),
                    tools=_TOOLS,
                    messages=messages,
                    **thinking_param,
                )
                print(".", end="", flush=True)

                u = resp.usage
                usage.input_tokens      += u.input_tokens
                usage.output_tokens     += u.output_tokens
                usage.cache_read_tokens += getattr(u, "cache_read_input_tokens", 0)

                for block in resp.content:
                    if block.type == "text":
                        final_text += block.text
                    elif block.type == "thinking":
                        final_thinking += getattr(block, "thinking", "")

                tool_calls = [b for b in resp.content if b.type == "tool_use"]
                if not tool_calls or resp.stop_reason == "end_turn":
                    break

                tool_results = []
                for call in tool_calls:
                    result = self._execute_tool(call)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": result,
                    })
                    if call.name == "write_file" and result.startswith("ERROR"):
                        write_fail_streak += 1
                        print(f"\n    ✗ write_file failed ({write_fail_streak}/{_WRITE_FAIL_THRESHOLD}): {result}", flush=True)
                        if write_fail_streak >= _WRITE_FAIL_THRESHOLD:
                            raise RuntimeError(f"write_file failed {write_fail_streak} times in a row: {result}")
                    elif call.name == "write_file":
                        write_fail_streak = 0

                messages.append({"role": "assistant", "content": resp.content})
                messages.append({"role": "user",      "content": tool_results})

        except Exception as exc:
            try:
                self._emergency_dump(final_text, final_thinking, exc)
            except Exception as dump_err:
                print(f"\n    ⚠  emergency dump 실패: {dump_err}", flush=True)
            raise

        print()
        return final_text, usage
