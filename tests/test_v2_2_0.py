"""Tests for the v2.2.0 savings: one close-out command, the goal and non-goals in tasks.json, free verification of
tasks that don't touch app code, and the Claude Code docs fetched only when needed.

Run from the repo root:  python -m unittest discover -s tests -q
"""
import json
import subprocess
import unittest
from pathlib import Path

from test_harness import PY, ROOT, Project, git, run


def tasks_json(p):
    return json.loads((p.dir / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))["master"]


def task(p, tid):
    return next(t for t in tasks_json(p)["tasks"] if t["id"] == tid)


class Close(unittest.TestCase):
    """A: `tasks.py close` = log + done + render + stage + untracked check + commit + push, in one call."""

    def setUp(self):
        self.p = Project()
        git(self.p.dir, "checkout", "-q", "-b", "phase-0")
        self.p.tasks("set-status", "1", "in-progress")
        (self.p.dir / "backend/app.py").write_text("app = 1\n", encoding="utf-8")

    def tearDown(self):
        self.p.cleanup()

    def head(self):
        return run(["git", "log", "-1", "--format=%B"], self.p.dir).stdout

    def test_close_does_the_whole_close_out(self):
        r = self.p.tasks("close", "1", "--tier", "sonnet", "--escalated-from", "haiku", "--files", "backend/app.py",
                         "--trailer", "Co-Authored-By: Claude <noreply@anthropic.com>")
        self.assertIn("closed 1", r.stdout)
        t = task(self.p, 1)
        self.assertEqual(t["status"], "done")
        self.assertIn("done by sonnet, escalated from haiku; verified", t["details"])
        self.assertIn("[x] **1.", (self.p.dir / "TASKS.md").read_text(encoding="utf-8"))
        msg = self.head()
        self.assertTrue(msg.startswith("task 1: Scaffold backend and frontend\n"), msg)
        self.assertIn("\n\nCo-Authored-By: Claude <noreply@anthropic.com>", msg)
        self.assertEqual(run(["git", "status", "--porcelain"], self.p.dir).stdout, "", "tree clean")
        self.assertIn("no origin remote", r.stdout)

    def test_unlisted_new_file_stops_the_commit(self):
        (self.p.dir / "backend/forgotten.py").write_text("x = 1\n", encoding="utf-8")
        r = self.p.tasks("close", "1", "--tier", "haiku", "--files", "backend/app.py", check=False)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("backend/forgotten.py", r.stdout)
        self.assertEqual(self.head().splitlines()[0], "bootstrap", "nothing committed")
        r = self.p.tasks("close", "1", "--tier", "haiku", "--files", "backend/app.py,backend/forgotten.py")
        self.assertIn("closed 1", r.stdout)
        self.assertEqual(task(self.p, 1)["details"].count("done by haiku"), 1, "logged once")

    def test_human_tasks_and_the_default_branch_are_refused(self):
        r = self.p.tasks("close", "5", "--tier", "haiku", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("human", r.stderr)
        git(self.p.dir, "stash", "-q", "-u")
        git(self.p.dir, "checkout", "-q", "-")
        r = self.p.tasks("close", "1", "--tier", "haiku", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("default branch", r.stderr)

    def test_script_task_already_marked_done_is_committed(self):
        tj = self.p.dir / ".taskmaster/tasks/tasks.json"
        data = json.loads(tj.read_text())
        data["master"]["tasks"][0]["status"] = "done"
        tj.write_text(json.dumps(data))
        (self.p.dir / "backend/app.py").unlink()
        self.p.tasks("close", "1", "--tier", "script")
        self.assertEqual(self.head().splitlines()[0], "task 1: Scaffold backend and frontend (script check)")


class GoalInTasks(unittest.TestCase):
    """B: agents get the goal and non-goals from `tasks.py show`, not by opening the PRD."""

    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.cleanup()

    def test_meta_sets_goal_and_show_prints_it(self):
        self.p.tasks("meta", "--goal", "Track daily habits on a phone.", "--non-goal", "No accounts",
                     "--non-goal", "No sync")
        meta = tasks_json(self.p)["metadata"]
        self.assertEqual(meta["goal"], "Track daily habits on a phone.")
        self.assertEqual(meta["non_goals"], ["No accounts", "No sync"])
        out = self.p.tasks("show", "2").stdout
        self.assertIn("goal: Track daily habits on a phone.", out)
        self.assertIn("non-goals: No accounts; No sync", out)
        self.assertIn("goal: Track daily habits", self.p.tasks("next", "--details").stdout)

    def test_validate_warns_without_a_goal(self):
        tj = self.p.dir / ".taskmaster/tasks/tasks.json"
        data = json.loads(tj.read_text())
        data["master"]["metadata"].pop("goal", None)
        tj.write_text(json.dumps(data))
        self.assertIn("metadata.goal", self.p.tasks("validate", check=False).stdout)

    def test_next_details_prints_what_show_prints(self):
        out = self.p.tasks("next", "--details").stdout
        self.assertIn("test strategy:", out)
        self.assertIn("description:", out)

    def test_instructions_no_longer_send_every_agent_to_the_prd(self):
        agents_md = (ROOT / "template/AGENTS.md.tmpl").read_text(encoding="utf-8")
        self.assertNotIn("Read Goal and Non-goals every session", agents_md)
        for b in ("haiku", "sonnet", "opus"):
            self.assertNotIn("prd.md", (ROOT / f"template/.claude/agents/builder-{b}.md").read_text(encoding="utf-8"))
        self.assertIn("tasks.py meta", (ROOT / "template/.claude/skills/plan-from-prd/SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("tasks.py meta", (ROOT / "template/.claude/skills/adapt/SKILL.md").read_text(encoding="utf-8"))


class FreeVerification(unittest.TestCase):
    """C: a task with `verify` commands whose changes touch no app code is verified by run_checks.py, no model."""

    def setUp(self):
        self.p = Project()
        d = self.p.dir
        (d / "tests").mkdir()
        (d / "tests/ok.py").write_text("print('ok')\n", encoding="utf-8")
        (d / "tests/bad.py").write_text("import sys\nsys.exit(4)\n", encoding="utf-8")
        cj = d / ".taskmaster/checks.json"
        cfg = json.loads(cj.read_text())
        cfg["allow"].append(Path(PY).stem.lower())
        cj.write_text(json.dumps(cfg))
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "checks")
        self.py = Path(PY).stem.lower()

    def tearDown(self):
        self.p.cleanup()

    def set_verify(self, tid, *cmds):
        tj = self.p.dir / ".taskmaster/tasks/tasks.json"
        data = json.loads(tj.read_text())
        next(t for t in data["master"]["tasks"] if t["id"] == tid)["verify"] = list(cmds)
        tj.write_text(json.dumps(data))

    def verify(self, tid):
        return run([PY, ".taskmaster/run_checks.py", "verify", str(tid)], self.p.dir, check=False)

    def test_tests_only_change_passes_without_a_model(self):
        self.set_verify(2, [self.py, "tests/ok.py"])
        (self.p.dir / "tests/test_new.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
        r = self.verify(2)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("verified by script", task(self.p, 2)["details"])
        self.assertEqual(task(self.p, 2)["status"], "pending", "verify never marks done; close does")

    def test_app_code_change_needs_the_verifier_agent(self):
        self.set_verify(2, [self.py, "tests/ok.py"])
        (self.p.dir / "backend/main.py").write_text("print('changed')\n", encoding="utf-8")
        r = self.verify(2)
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("backend/main.py", r.stdout)
        self.assertIn("verifier agent", r.stdout)

    def test_safe_paths_edited_by_the_builder_do_not_count(self):
        self.set_verify(2, [self.py, "tests/ok.py"])
        hj = self.p.dir / ".claude/harness.json"
        h = json.loads(hj.read_text())
        h["safe_paths"].append("backend/**")
        hj.write_text(json.dumps(h))
        (self.p.dir / "backend/main.py").write_text("print('changed')\n", encoding="utf-8")
        self.assertEqual(self.verify(2).returncode, 3)

    def test_failing_command_is_a_fail_and_bad_commands_are_refused(self):
        self.set_verify(2, [self.py, "tests/bad.py"])
        r = self.verify(2)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("exit 4", r.stdout)
        self.set_verify(2, ["rm", "-rf", "tests"])
        self.assertEqual(self.verify(2).returncode, 2)

    def test_no_verify_commands_means_the_verifier_agent(self):
        self.assertEqual(self.verify(2).returncode, 3)

    def test_validate_checks_verify_like_check(self):
        self.set_verify(2, "pytest -q && ruff")
        self.assertIn("2: verify:", self.p.tasks("validate", check=False).stdout)

    def test_add_accepts_verify(self):
        self.p.tasks("add", "--title", "Docs", "--phase", "0", "--verify", "python tests/ok.py")
        self.assertEqual(tasks_json(self.p)["tasks"][-1]["verify"], [["python", "tests/ok.py"]])

    def test_next_task_uses_it_and_keeps_the_verifier_for_app_code(self):
        nt = (ROOT / "template/.claude/skills/next-task/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("run_checks.py verify", nt)
        self.assertIn("tasks.py close", nt)


class DocsFetchOnDemand(unittest.TestCase):
    """E: BOOTSTRAP fetches the Claude Code docs only when check_harness reports an unknown field."""

    def test_bootstrap(self):
        b = (ROOT / "BOOTSTRAP.md").read_text(encoding="utf-8")
        step4 = b.split("## 4.")[1].split("## 5.")[0]
        self.assertIn("unknown agent field", step4)
        self.assertIn("Skip", step4)


if __name__ == "__main__":
    unittest.main()
