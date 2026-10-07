import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(ROOT, "install.sh")
IMPORT_LINE = "@" + os.path.join(ROOT, "instructions.md")


class InstallTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = self._tmp.name
        self.claude = os.path.join(base, "claude")
        self.bin = os.path.join(base, "bin")
        self.env = dict(os.environ, CLAUDE_HOME=self.claude, WB_BIN_DIR=self.bin,
                        CODEX_HOME=os.path.join(base, "no-codex"))

    def tearDown(self):
        self._tmp.cleanup()

    def run_install(self, *args):
        r = subprocess.run([INSTALL, *args], env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def claude_md(self):
        return os.path.join(self.claude, "CLAUDE.md")

    def test_link_creates_symlinks_and_is_idempotent(self):
        self.run_install("link")
        self.assertEqual(os.readlink(self.claude_md()), os.path.join(ROOT, "instructions.md"))
        self.assertTrue(os.path.islink(os.path.join(self.claude, "skills", "handoff")))
        self.assertTrue(os.path.islink(os.path.join(self.bin, "wb")))
        second = self.run_install("link")
        self.assertFalse([l for l in second.splitlines() if l.startswith(("linked", "skip"))])

    def test_dry_run_changes_nothing(self):
        out = self.run_install("link", "--dry-run")
        self.assertIn("would:", out)
        self.assertFalse(os.path.exists(self.claude))

    def test_existing_file_is_a_conflict_not_overwritten(self):
        os.makedirs(self.claude)
        with open(self.claude_md(), "w") as fh:
            fh.write("mine\n")
        out = self.run_install("link")
        self.assertIn("skip", out)
        with open(self.claude_md()) as fh:
            self.assertEqual(fh.read(), "mine\n")

    def test_import_mode_appends_once_and_unlink_removes(self):
        os.makedirs(self.claude)
        with open(self.claude_md(), "w") as fh:
            fh.write("platform instructions\n")
        self.run_install("link", "--import-instructions")
        self.run_install("link", "--import-instructions")
        with open(self.claude_md()) as fh:
            text = fh.read()
        self.assertEqual(text.count(IMPORT_LINE), 1)
        self.assertIn("platform instructions", text)
        self.assertIn("imported", self.run_install("status", "--import-instructions"))
        self.run_install("unlink", "--import-instructions")
        with open(self.claude_md()) as fh:
            self.assertEqual(fh.read().strip(), "platform instructions")

    def test_import_mode_still_links_when_no_file_exists(self):
        self.run_install("link", "--import-instructions")
        self.assertTrue(os.path.islink(self.claude_md()))

    def test_import_mode_never_edits_through_a_foreign_symlink(self):
        os.makedirs(self.claude)
        other = os.path.join(self._tmp.name, "dotfiles-claude.md")
        with open(other, "w") as fh:
            fh.write("dotfiles\n")
        os.symlink(other, self.claude_md())
        self.run_install("link", "--import-instructions")
        with open(other) as fh:
            self.assertEqual(fh.read(), "dotfiles\n")

    def test_unknown_flag_fails(self):
        r = subprocess.run([INSTALL, "link", "--nope"], env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
