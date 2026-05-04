"""
Tests for BaseAgent safety fixes (GitHub issue #1).

Gap ①  thinking blocks are captured and preserved in emergency dump
Gap ②  consecutive write_file failures are detected and abort immediately
Gap ③  any unhandled exception triggers an emergency dump without masking itself
"""

from unittest.mock import MagicMock, patch
import pytest

from agents.base import BaseAgent, _WRITE_FAIL_THRESHOLD


# ── Concrete test subclass ─────────────────────────────────────────────────────

class _Agent(BaseAgent):
    ROLE = "planner"


# ── Response / block factories ─────────────────────────────────────────────────

def _resp(content, stop_reason="end_turn"):
    r = MagicMock()
    r.content = content
    r.stop_reason = stop_reason
    r.usage = MagicMock(input_tokens=10, output_tokens=5, cache_read_input_tokens=0)
    return r


def _text(text):
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _thinking(thought):
    b = MagicMock()
    b.type = "thinking"
    b.thinking = thought
    return b


def _tool(name, inp=None, id="t1"):
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = inp or {"path": "out.txt", "content": "x"}
    b.id = id
    return b


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_system_prompt():
    """Suppress file I/O from _load_system_prompt for every test."""
    with patch.object(_Agent, "_load_system_prompt", return_value="sys"):
        yield


# ── Helper ─────────────────────────────────────────────────────────────────────

def _agent(tmp_path, side_effects):
    a = _Agent(project_root=tmp_path)
    a._api_call = MagicMock(side_effect=side_effects)
    return a


# ══════════════════════════════════════════════════════════════════════════════
# Gap ①: thinking block capture
# ══════════════════════════════════════════════════════════════════════════════

class TestThinkingCapture:

    def test_thinking_preserved_in_emergency_dump(self, tmp_path):
        """Thinking content must appear in dump when write_file fails twice."""
        a = _agent(tmp_path, [
            _resp([_thinking("deep thought"), _tool("write_file", id="t1")], "tool_use"),
            _resp([_tool("write_file", id="t2")], "tool_use"),
        ])
        a._execute_tool = MagicMock(return_value="ERROR: permission denied")

        with pytest.raises(RuntimeError):
            a._run("prompt")

        dumps = list(tmp_path.glob("emergency_dump_planner_*.md"))
        assert dumps, "dump file was not created"
        assert "deep thought" in dumps[0].read_text()

    def test_multiple_thinking_blocks_across_rounds_all_accumulated(self, tmp_path):
        """Thinking from every API round must all be present in the dump."""
        a = _agent(tmp_path, [
            _resp([_thinking("part 1"), _tool("write_file", id="t1")], "tool_use"),
            _resp([_thinking("part 2"), _tool("write_file", id="t2")], "tool_use"),
        ])
        a._execute_tool = MagicMock(return_value="ERROR: permission denied")

        with pytest.raises(RuntimeError):
            a._run("prompt")

        content = list(tmp_path.glob("emergency_dump_planner_*.md"))[0].read_text()
        assert "part 1" in content
        assert "part 2" in content

    def test_empty_thinking_omits_thinking_section_from_dump(self, tmp_path):
        """When no thinking blocks were produced, ## Thinking must not appear in dump."""
        a = _agent(tmp_path, [
            _resp([_text("intro"), _tool("write_file", id="t1")], "tool_use"),
            _resp([_tool("write_file", id="t2")], "tool_use"),
        ])
        a._execute_tool = MagicMock(return_value="ERROR: permission denied")

        with pytest.raises(RuntimeError):
            a._run("prompt")

        content = list(tmp_path.glob("emergency_dump_planner_*.md"))[0].read_text()
        assert "## Thinking" not in content

    def test_thinking_not_leaked_into_return_value_on_success(self, tmp_path):
        """On a normal run, thinking must not bleed into the returned text."""
        a = _agent(tmp_path, [
            _resp([_thinking("internal reasoning"), _text("final answer")], "end_turn"),
        ])

        text, _ = a._run("prompt")

        assert "internal reasoning" not in text
        assert text == "final answer"
        assert not list(tmp_path.glob("emergency_dump_*.md"))


# ══════════════════════════════════════════════════════════════════════════════
# Gap ②: write_file failure streak
# ══════════════════════════════════════════════════════════════════════════════

class TestWriteFailStreak:

    def test_threshold_constant_is_two(self):
        """Document the abort threshold as an explicit contract."""
        assert _WRITE_FAIL_THRESHOLD == 2

    def test_two_consecutive_failures_raise_and_create_dump(self, tmp_path):
        a = _agent(tmp_path, [
            _resp([_tool("write_file", id="t1")], "tool_use"),
            _resp([_tool("write_file", id="t2")], "tool_use"),
        ])
        a._execute_tool = MagicMock(return_value="ERROR: permission denied")

        with pytest.raises(RuntimeError, match="write_file failed 2 times"):
            a._run("prompt")

        assert list(tmp_path.glob("emergency_dump_planner_*.md"))

    def test_one_failure_does_not_raise(self, tmp_path):
        """A single write failure followed by end_turn must complete normally."""
        a = _agent(tmp_path, [
            _resp([_tool("write_file", id="t1")], "tool_use"),
            _resp([_text("done")], "end_turn"),
        ])
        a._execute_tool = MagicMock(return_value="ERROR: permission denied")

        text, _ = a._run("prompt")
        assert text == "done"

    def test_streak_resets_on_success_so_alternating_failures_are_tolerated(self, tmp_path):
        """fail → success → fail must NOT reach the threshold (streak resets at success)."""
        call_count = [0]

        def _execute(call):
            call_count[0] += 1
            # calls 1 and 3 fail, call 2 succeeds
            if call_count[0] in (1, 3):
                return "ERROR: transient"
            return f"OK: wrote {call.input['path']}"

        a = _agent(tmp_path, [
            _resp([_tool("write_file", id="t1")], "tool_use"),
            _resp([_tool("write_file", id="t2")], "tool_use"),
            _resp([_tool("write_file", id="t3")], "tool_use"),
            _resp([_text("done")], "end_turn"),
        ])
        a._execute_tool = _execute

        text, _ = a._run("prompt")
        assert text == "done"

    def test_non_write_tool_between_failures_does_not_reset_streak(self, tmp_path):
        """write_fail → read_file → write_fail must still trigger RuntimeError."""
        results = iter([
            "ERROR: denied",  # write_file round 1
            "file content",   # read_file  round 2  (does not reset streak)
            "ERROR: denied",  # write_file round 3  (streak → 2)
        ])

        def _execute(call):
            return next(results)

        a = _agent(tmp_path, [
            _resp([_tool("write_file", id="t1")], "tool_use"),
            _resp([_tool("read_file", inp={"path": "x.txt"}, id="t2")], "tool_use"),
            _resp([_tool("write_file", id="t3")], "tool_use"),
        ])
        a._execute_tool = _execute

        with pytest.raises(RuntimeError):
            a._run("prompt")

    def test_two_simultaneous_failures_in_one_batch_raise(self, tmp_path):
        """Two write_file failures in the same tool_calls list must trigger abort."""
        a = _agent(tmp_path, [
            _resp([_tool("write_file", id="t1"), _tool("write_file", id="t2")], "tool_use"),
        ])
        a._execute_tool = MagicMock(return_value="ERROR: permission denied")

        with pytest.raises(RuntimeError):
            a._run("prompt")


# ══════════════════════════════════════════════════════════════════════════════
# Gap ③: emergency dump
# ══════════════════════════════════════════════════════════════════════════════

class TestEmergencyDump:

    def test_unexpected_api_exception_triggers_dump_and_reraises(self, tmp_path):
        a = _agent(tmp_path, [RuntimeError("unexpected api error")])

        with pytest.raises(RuntimeError, match="unexpected api error"):
            a._run("prompt")

        assert list(tmp_path.glob("emergency_dump_planner_*.md"))

    def test_dump_failure_does_not_mask_original_exception(self, tmp_path):
        """If _emergency_dump itself fails, the original exception must still propagate."""
        a = _agent(tmp_path, [ValueError("original")])

        with patch.object(a, "_emergency_dump", side_effect=OSError("disk full")):
            with pytest.raises(ValueError, match="original"):
                a._run("prompt")

    def test_no_content_captured_when_exception_fires_before_any_response(self, tmp_path):
        """When the exception precedes any API response, dump must say no content captured."""
        a = _agent(tmp_path, [RuntimeError("instant fail")])

        with pytest.raises(RuntimeError):
            a._run("prompt")

        content = list(tmp_path.glob("emergency_dump_planner_*.md"))[0].read_text()
        assert "no content captured" in content

    def test_dump_filename_matches_expected_pattern(self, tmp_path):
        a = _agent(tmp_path, [RuntimeError("fail")])

        with pytest.raises(RuntimeError):
            a._run("prompt")

        dumps = list(tmp_path.glob("emergency_dump_planner_*.md"))
        assert len(dumps) == 1
        name = dumps[0].name
        assert name.startswith("emergency_dump_planner_")
        assert name.endswith(".md")

    def test_no_dump_created_on_successful_run(self, tmp_path):
        a = _agent(tmp_path, [
            _resp([_text("success")], "end_turn"),
        ])

        a._run("prompt")

        assert not list(tmp_path.glob("emergency_dump_*.md"))
