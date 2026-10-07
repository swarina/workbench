import json
import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = os.path.join(ROOT, "cloud", "setup.sh")


class CloudSetupTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = self._tmp.name
        self.claude = os.path.join(base, "claude")
        os.makedirs(self.claude)
        with open(os.path.join(self.claude, "CLAUDE.md"), "w") as fh:
            fh.write("platform instructions\n")
        self.env = dict(os.environ, CLAUDE_HOME=self.claude, WB_BIN_DIR=os.path.join(base, "bin"),
                        CODEX_HOME=os.path.join(base, "no-codex"))

    def tearDown(self):
        self._tmp.cleanup()

    def run_setup(self):
        r = subprocess.run([SETUP], env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def read(self, *parts):
        with open(os.path.join(self.claude, *parts)) as fh:
            return fh.read()

    def test_installs_everything_without_replacing_platform_claude_md(self):
        self.run_setup()
        claude_md = self.read("CLAUDE.md")
        self.assertIn("platform instructions", claude_md)
        self.assertIn("@" + os.path.join(ROOT, "instructions.md"), claude_md)
        self.assertTrue(os.path.islink(os.path.join(self.claude, "skills", "handoff")))
        hook = os.path.join(ROOT, "hooks", "context-nudge")
        settings = json.loads(self.read("settings.json"))
        self.assertEqual(settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"], hook)
        self.assertTrue(os.path.exists(os.path.join(self.claude, ".workbench-cloud")))

    def test_rerun_is_idempotent(self):
        self.run_setup()
        first = (self.read("CLAUDE.md"), self.read("settings.json"))
        self.run_setup()
        self.assertEqual((self.read("CLAUDE.md"), self.read("settings.json")), first)

    def test_never_fails_the_session_even_with_broken_settings(self):
        with open(os.path.join(self.claude, "settings.json"), "w") as fh:
            fh.write("{broken")
        out = self.run_setup()
        self.assertIn("failed, continuing", out)
        self.assertEqual(self.read("settings.json"), "{broken")


if __name__ == "__main__":
    unittest.main()
