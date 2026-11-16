"""v2.2.1: a project's own Python linter must not fail CI on the harness's scripts.

Reproduces coursera-dl: pyproject.toml with a strict ruff config (line-length 100, E/F/W/I/B/UP/S) linted the
harness files in .taskmaster/ and .claude/ and failed every CI job with 226 errors.

Run from the repo root:  python -m unittest discover -s tests -q
"""
import shutil
import subprocess
import sys
import unittest

from test_harness import PY, ROOT, Project

STRICT = """[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "S"]
ignore = ["S101"]
"""


def ruff():
    """ruff as a module of this Python, or on PATH (CI installs it for this test only)."""
    if subprocess.run([PY, "-m", "ruff", "--version"], capture_output=True).returncode == 0:
        return [PY, "-m", "ruff"]
    return [shutil.which("ruff")] if shutil.which("ruff") else None


class ProjectLinterIgnoresHarnessStyle(unittest.TestCase):
    def test_template_ships_its_own_lint_config(self):
        for d in ("template/.taskmaster", "template/.claude"):
            cfg = (ROOT / d / "ruff.toml").read_text(encoding="utf-8")
            self.assertIn("line-length = 120", cfg, d)
            self.assertIn('select = ["E9", "F"]', cfg, d)

    @unittest.skipIf(ruff() is None, "ruff not installed (CI installs it)")
    def test_strict_project_ruff_passes_on_a_fresh_install(self):
        p = Project()
        try:
            (p.dir / "pyproject.toml").write_text(STRICT, encoding="utf-8")
            r = subprocess.run(ruff() + ["check", "."], cwd=p.dir, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 0, r.stdout[-2000:])
        finally:
            p.cleanup()

    @unittest.skipIf(ruff() is None, "ruff not installed (CI installs it)")
    def test_real_bugs_in_harness_files_are_still_caught(self):
        p = Project()
        try:
            (p.dir / "pyproject.toml").write_text(STRICT, encoding="utf-8")
            with open(p.dir / ".taskmaster/tasks.py", "a", encoding="utf-8", newline="\n") as f:
                f.write("\nprint(undefined_name)\n")
            r = subprocess.run(ruff() + ["check", "."], cwd=p.dir, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("F821", r.stdout)
        finally:
            p.cleanup()


if __name__ == "__main__":
    unittest.main()
