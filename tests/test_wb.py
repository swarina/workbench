import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wb import check, detectors, live, report, statusline  # noqa: E402
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
            "gitBranch": "feat/x",
            "message": {"id": msg_id, "model": "m", "content": blocks,
                        "usage": {"input_tokens": 1, "cache_read_input_tokens": cache_read,
                                  "cache_creation_input_tokens": 10, "output_tokens": 5,
                                  "cache_creation": {"ephemeral_5m_input_tokens": 4,
                                                     "ephemeral_1h_input_tokens": 6}}}}


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
        self.assertEqual((s.turns[0].cache_write_5m, s.turns[0].cache_write_1h), (4, 6))
        self.assertEqual(s.turns[0].branch, "feat/x")

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


def ts(seconds):
    return "2026-01-01T%02d:%02d:%02dZ" % (seconds // 3600, seconds % 3600 // 60, seconds % 60)


class CacheRewriteTest(unittest.TestCase):
    def turns(self, gap, second_write=100_000, second_read=0, one_hour=True):
        big = dict(cache_read=100_000)
        first = Turn(timestamp=ts(0), cache_write=1_000, cache_write_1h=1_000 if one_hour else 0,
                     cache_write_5m=0 if one_hour else 1_000, **big)
        second = Turn(timestamp=ts(gap), cache_write=second_write, cache_read=second_read)
        return Session("claude", "s", "p", turns=[first, second])

    def names(self, s):
        return {f.detector for f in detectors.run_all(s)}

    def test_idle_expiry_over_ttl(self):
        self.assertIn("cache_rewrite", self.names(self.turns(gap=7200, second_read=20_000)))

    def test_within_one_hour_ttl_is_invalidation(self):
        found = self.names(self.turns(gap=1800, second_read=20_000))
        self.assertIn("cache_invalidation", found)
        self.assertNotIn("cache_rewrite", found)

    def test_five_minute_ttl_expires_sooner(self):
        found = self.names(self.turns(gap=1800, second_read=20_000, one_hour=False))
        self.assertIn("cache_rewrite", found)

    def test_compaction_is_not_a_rewrite(self):
        s = self.turns(gap=7200, second_write=60_000)
        self.assertNotIn("cache_rewrite", self.names(s))
        self.assertNotIn("cache_invalidation", self.names(s))

    def test_small_contexts_ignored(self):
        s = Session("claude", "s", "p", turns=[Turn(timestamp=ts(0), cache_read=20_000),
                                               Turn(timestamp=ts(9000), cache_write=20_000)])
        self.assertEqual(self.names(s), set())

    def test_split_changes_cost(self):
        flat = Turn(cache_write=1000)
        split = Turn(cache_write=1000, cache_write_1h=1000)
        self.assertGreater(split.cost_units, flat.cost_units)


class StartupOverheadTest(unittest.TestCase):
    def test_flags_heavy_first_turn(self):
        heavy = Session("claude", "s", "p", turns=[Turn(cache_write=60_000), Turn(cache_read=60_000)])
        light = Session("claude", "s", "p", turns=[Turn(cache_write=10_000)])
        self.assertIn("startup_overhead", {f.detector for f in detectors.run_all(heavy)})
        self.assertNotIn("startup_overhead", {f.detector for f in detectors.run_all(light)})

    def test_timestamp_parsing(self):
        from wb.model import parse_timestamp
        self.assertEqual(parse_timestamp("1970-01-01T00:01:00.500Z"), 60)
        self.assertIsNone(parse_timestamp("garbage"))
        self.assertIsNone(parse_timestamp(""))


class ReportTest(unittest.TestCase):
    def test_summary_renders(self):
        s = Session("claude", "s", "p", project="proj", turns=[Turn(cache_read=500_000, out=10)])
        summary = report.summarize([s], detectors.run_all(s))
        self.assertAlmostEqual(sum(summary["cost_share"].values()), 1.0, places=2)
        self.assertIn("long_session", report.render_summary(summary))
        self.assertIn("SESSION s", report.render_session(s, detectors.run_all(s)))


class BreakdownTest(unittest.TestCase):
    def setUp(self):
        a = Session("claude", "a", "p", project="proj", turns=[
            Turn(cache_write=60_000, model="opus", branch="feat/a"),
            Turn(cache_read=60_000, model="opus", branch="feat/a")])
        b = Session("claude", "b", "p", project="proj", kind="subagent", turns=[
            Turn(cache_write=5_000, model="haiku", branch="main")])
        self.summary = report.summarize([a, b], [])

    def test_kind_and_model_shares_sum_to_one(self):
        self.assertAlmostEqual(sum(self.summary["cost_by_kind"].values()), 1.0, places=2)
        self.assertAlmostEqual(sum(self.summary["cost_by_model"].values()), 1.0, places=2)
        self.assertEqual(next(iter(self.summary["cost_by_model"])), "opus")

    def test_startup_context_per_project(self):
        self.assertEqual(self.summary["projects"]["proj"]["startup_p50"], 60_000)

    def test_branches_sorted_by_cost(self):
        self.assertEqual(self.summary["branches"][0]["branch"], "feat/a")
        self.assertIn("proj:feat/a", report.render_branches(self.summary))


class CompareTest(unittest.TestCase):
    def snapshot(self, peak, turns=100):
        s = Session("claude", "s", "p", turns=[Turn(cache_read=peak) for _ in range(turns)])
        return report.summarize([s], detectors.run_all(s))

    def test_improvement_and_regression_labelled(self):
        from wb import compare
        text = compare.compare(self.snapshot(500_000), self.snapshot(100_000))
        peak_row = [line for line in text.splitlines() if line.startswith("peak context p50")][0]
        self.assertIn("better", peak_row)
        self.assertIn("worse", compare.compare(self.snapshot(100_000), self.snapshot(500_000)))

    def test_new_waste_detector_row(self):
        from wb import compare
        text = compare.compare(self.snapshot(100_000), self.snapshot(500_000))
        self.assertIn("waste/1k turns: long_session", text)

    def test_save_and_resolve_by_name(self):
        from wb import compare
        with tempfile.TemporaryDirectory() as home:
            os.environ["WB_HOME"] = home
            try:
                path = compare.save(self.snapshot(100_000), "baseline")
                self.assertEqual(compare.resolve("baseline"), path)
                self.assertEqual(compare.load("baseline")["sessions"], 1)
                with self.assertRaises(FileNotFoundError):
                    compare.resolve("nope")
            finally:
                del os.environ["WB_HOME"]


def transcript_with_context(tokens, padding_lines=0):
    records = [{"type": "user", "message": {"content": "pad" * 100}}] * padding_lines
    records.append(assistant("m1", [{"type": "text", "text": "hi"}], cache_read=tokens))
    return write_jsonl(records)


class LiveTest(unittest.TestCase):
    def test_latest_context_reads_last_assistant_turn(self):
        path = write_jsonl([assistant("m1", [], cache_read=1_000), assistant("m2", [], cache_read=5_000)])
        self.assertEqual(live.latest_context(path), 5_000 + 10 + 1)

    def test_latest_context_handles_missing_and_cut_lines(self):
        self.assertIsNone(live.latest_context("/nonexistent/file.jsonl"))
        big = transcript_with_context(7_000, padding_lines=5_000)  # forces a cut first line
        self.assertEqual(live.latest_context(big), 7_011)

    def test_bands(self):
        self.assertEqual(live.status_band(100_000), "ok")
        self.assertEqual(live.status_band(200_000), "soon")
        self.assertEqual(live.status_band(350_000), "now")
        self.assertEqual(live.nudge_band(250_000), "soon")
        self.assertEqual(live.nudge_band(450_000), "now")

    def test_statusline_renders_and_degrades(self):
        path = transcript_with_context(184_000)
        line = statusline.render({"transcript_path": path, "cost": {"total_cost_usd": 3.1},
                                  "context_window": {"context_window_size": 1_000_000}})
        self.assertEqual(line, "ctx 184k (18%) | $3.10 | handoff soon")
        self.assertEqual(statusline.render({}), "")
        self.assertEqual(statusline.render({"transcript_path": path}), "ctx 184k | handoff soon")


class NudgeTest(unittest.TestCase):
    def payload(self, tokens, session="s1"):
        return {"transcript_path": transcript_with_context(tokens), "session_id": session}

    def test_silent_when_small_or_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(live.nudge(self.payload(50_000), d), "")
            self.assertEqual(live.nudge({"transcript_path": "/nope"}, d), "")
            self.assertEqual(live.nudge({}, d), "")

    def test_nudges_once_then_rate_limits_then_escalates(self):
        with tempfile.TemporaryDirectory() as d:
            soon = self.payload(250_000)
            self.assertIn("next natural boundary", live.nudge(soon, d))
            for _ in range(live.LIVE["nudge_every"] - 1):
                self.assertEqual(live.nudge(soon, d), "")
            self.assertIn("next natural boundary", live.nudge(soon, d))
            self.assertIn("now, before other work", live.nudge(self.payload(450_000), d))

    def test_sessions_are_independent(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertNotEqual(live.nudge(self.payload(250_000, "a"), d), "")
            self.assertNotEqual(live.nudge(self.payload(250_000, "b"), d), "")

    def test_hook_script_exits_zero_on_garbage(self):
        import subprocess
        hook = os.path.join(ROOT, "hooks", "context-nudge")
        for stdin in ("not json", "", "{}"):
            r = subprocess.run([sys.executable, hook], input=stdin, capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout), (0, ""))


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
