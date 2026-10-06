import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wb import check, detectors, report  # noqa: E402
from wb.model import Session, ToolCall, Turn  # noqa: E402
from wb.sources import claude, codex  # noqa: E402


def write_jsonl(records):
    fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in records:
        fh.write(json.dumps(r) + "\n")
    fh.close()
    return fh.name


def assistant(msg_id, blocks, cache_read=1000):
    return {"type": "assistant", "cwd": "/x/proj", "timestamp": "2026-01-01T00:00:00Z",
            "message": {"id": msg_id, "model": "m", "content": blocks,
                        "usage": {"input_tokens": 1, "cache_read_input_tokens": cache_read,
                                  "cache_creation_input_tokens": 10, "output_tokens": 5}}}


def tool_use(tid, name, **inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def tool_result(tid, text):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": text}]}]}}


class ClaudeSourceTest(unittest.TestCase):
    def test_dedupes_usage_and_attaches_results(self):
        path = write_jsonl([
            assistant("m1", [{"type": "text", "text": "hi"}]),
            assistant("m1", [tool_use("t1", "Bash", command="cd /x && git diff --stat")]),
            tool_result("t1", "x" * 400),
            assistant("m2", [tool_use("t2", "Read", file_path="/x/a.py")]),
        ])
        s = claude.parse(path)
        self.assertEqual(len(s.turns), 2)
        self.assertEqual(s.total("cache_read"), 2000)
        self.assertEqual(s.project, "proj")
        self.assertEqual(s.calls[0].output_tokens, 100)
        self.assertEqual(s.calls[0].label, "$ git diff")
        self.assertEqual(s.calls[1].turn, 1)

    def test_empty_transcript_is_skipped(self):
        self.assertIsNone(claude.parse(write_jsonl([{"type": "mode"}])))


class CodexSourceTest(unittest.TestCase):
    def test_token_counts_and_calls(self):
        usage = {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 7}
        path = write_jsonl([
            {"type": "session_meta", "payload": {"cwd": "/x/proj"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": usage}}},
            {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "c1",
                                                  "name": "exec", "input": "ls"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "c1",
                                                  "output": "y" * 40}},
        ])
        s = codex.parse(path)
        self.assertEqual((s.turns[0].fresh_in, s.turns[0].cache_read), (40, 60))
        self.assertEqual(s.calls[0].output_tokens, 10)


class DetectorTest(unittest.TestCase):
    def session(self, turns=1, context=1000):
        return Session("claude", "s", "p", turns=[Turn(cache_read=context) for _ in range(turns)])

    def names(self, s):
        return {f.detector for f in detectors.run_all(s)}

    def test_clean_session_has_no_findings(self):
        self.assertEqual(self.names(self.session()), set())

    def test_long_session(self):
        s = self.session(turns=3, context=detectors.THRESHOLDS["long_session_peak"])
        self.assertIn("long_session", self.names(s))

    def test_repeat_reads_reset_by_edit(self):
        s = self.session()
        s.calls = [ToolCall("Read", 0, {"file_path": "a"}) for _ in range(3)]
        self.assertIn("repeat_reads", self.names(s))
        s.calls.insert(2, ToolCall("Edit", 0, {"file_path": "a"}))
        self.assertNotIn("repeat_reads", self.names(s))

    def test_large_outputs(self):
        s = self.session()
        s.calls = [ToolCall("Bash", 0, {"command": "git diff"}, output_chars=40_000)]
        self.assertIn("large_outputs", self.names(s))

    def test_unbatched_calls(self):
        s = self.session(turns=5)
        s.calls = [ToolCall("Read", i, {"file_path": str(i)}) for i in range(5)]
        self.assertIn("unbatched_calls", self.names(s))
        s.calls = [ToolCall("Read", 0, {"file_path": str(i)}) for i in range(5)]
        self.assertNotIn("unbatched_calls", self.names(s))


class ReportTest(unittest.TestCase):
    def test_summary_renders(self):
        s = Session("claude", "s", "p", project="proj", turns=[Turn(cache_read=500_000, out=10)])
        summary = report.summarize([s], detectors.run_all(s))
        self.assertAlmostEqual(sum(summary["cost_share"].values()), 1.0, places=2)
        self.assertIn("long_session", report.render_summary(summary))
        self.assertIn("SESSION s", report.render_session(s, detectors.run_all(s)))


class RepoTest(unittest.TestCase):
    def test_repo_passes_its_own_lint(self):
        self.assertEqual(check.check(ROOT), [])

    def test_lint_catches_bad_skill(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "skills", "x"))
            for rel, text in (("instructions.md", "ok\n"),
                              ("skills/x/SKILL.md", "---\nname: y\n---\n")):
                with open(os.path.join(d, rel), "w") as fh:
                    fh.write(text)
            problems = "\n".join(check.check(d))
            self.assertIn("missing 'description'", problems)
            self.assertIn("does not match directory", problems)


if __name__ == "__main__":
    unittest.main()
