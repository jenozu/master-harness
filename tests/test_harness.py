"""Tests for tasks.py, apply_template.py and check_harness.py (stdlib unittest).

Run from the repo root:  python -m unittest discover -s tests -q
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "sample"
PY = sys.executable


def run(args, cwd, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"{args} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


def git(cwd, *args):
    return run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd)


class Project:
    """A scratch project with the harness applied."""

    def __init__(self, rules="python-fastapi,react-vite-tailwind,pwa-mobile",
                 skills="db-migration,mobile-ui-check,vps", settings="python,node,vps"):
        self.dir = Path(tempfile.mkdtemp(prefix="harness-"))
        git(self.dir, "init", "-q")
        (self.dir / "backend").mkdir()
        (self.dir / "backend/main.py").write_text("print('hi')\n")
        (self.dir / "frontend/src").mkdir(parents=True)
        (self.dir / "frontend/src/App.jsx").write_text("export default () => null\n")
        self.apply_out = run([PY, str(ROOT / "scripts/apply_template.py"), "--target", str(self.dir),
                              "--values", str(FIX / "values.json"), "--rules", rules, "--skills", skills,
                              "--settings", settings], ROOT).stdout
        shutil.copy(FIX / "prd.md", self.dir / ".taskmaster/docs/prd.md")
        shutil.copy(FIX / "tasks.json", self.dir / ".taskmaster/tasks/tasks.json")
        run([PY, ".taskmaster/render_tasks_md.py"], self.dir)
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "bootstrap")

    def tasks(self, *args, check=True):
        return run([PY, ".taskmaster/tasks.py", *args], self.dir, check)

    def check(self, *extra):
        return run([PY, str(self.dir / ".claude/scripts/check_harness.py"), "--target", str(self.dir), *extra], ROOT, check=False)

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class ApplyAndCheck(unittest.TestCase):
    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.cleanup()

    def test_bootstrap_passes_checker(self):
        self.assertNotIn("UNFILLED", self.p.apply_out)
        r = self.p.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("harness OK", r.stdout)

    def test_files_and_values(self):
        d = self.p.dir
        claude = (d / "CLAUDE.md").read_text()
        self.assertIn("Habit Dots", claude)
        self.assertIn("@AGENTS.md", claude)
        self.assertEqual((d / ".claude/HARNESS_VERSION").read_text().strip(), (ROOT / "VERSION").read_text().strip())
        servers = json.loads((d / ".claude/dev-servers.json").read_text())
        self.assertEqual([s["name"] for s in servers], ["api", "web"])
        settings = json.loads((d / ".claude/settings.json").read_text())
        self.assertIn("Bash(pytest *)", settings["permissions"]["allow"])
        self.assertIn("Bash(npm install *)", settings["permissions"]["ask"])
        self.assertIn("- What domain will the app use?", (d / ".claude/rules/memory.md").read_text())
        self.assertIn(".harness-tmp/", (d / ".gitignore").read_text())
        self.assertTrue((d / ".claude/skills/vps/SKILL.md").exists())
        self.assertIn("ssh vps status habit-dots", (d / ".claude/skills/vps/SKILL.md").read_text())
        self.assertIn("Bash(ssh vps *)", settings["permissions"]["allow"])
        self.assertNotIn("Bash(ssh *)", settings["permissions"]["ask"], "ask beats allow: must not block ssh vps")
        self.assertNotIn("Bash(git push *)", settings["permissions"]["ask"])
        self.assertIn("Bash(git push origin *)", settings["permissions"]["ask"])

    def test_bootstrap_never_overwrites(self):
        d = self.p.dir
        (d / "CLAUDE.md").write_text("# mine\n@AGENTS.md\n")
        out = run([PY, str(ROOT / "scripts/apply_template.py"), "--target", str(d),
                   "--values", str(FIX / "values.json")], ROOT).stdout
        self.assertEqual((d / "CLAUDE.md").read_text(), "# mine\n@AGENTS.md\n")
        self.assertIn("kept existing", out)

    def test_checker_catches_problems(self):
        d = self.p.dir
        (d / "CLAUDE.md").write_text((d / "CLAUDE.md").read_text() + "\n{{LEFTOVER}}\n")
        agent = d / ".claude/agents/verifier.md"
        agent.write_text(agent.read_text().replace("color: yellow", "color: yellow\nbogusField: 1"))
        s = json.loads((d / ".claude/settings.json").read_text())
        s["env"] = {}
        (d / ".claude/settings.json").write_text(json.dumps(s))
        (d / "backend/new_untracked.py").write_text("x = 1\n")
        r = self.p.check()
        self.assertEqual(r.returncode, 1)
        for needle in ("LEFTOVER", "bogusField", "SPAWN_DEPTH", "not committed"):
            self.assertIn(needle, r.stdout)

    def test_checker_catches_secret_and_empty_plan(self):
        d = self.p.dir
        mem = d / ".claude/rules/memory.md"
        mem.write_text(mem.read_text() + "\n- key: sk-" + "a" * 30 + "\n")
        tj = d / ".taskmaster/tasks/tasks.json"
        data = json.loads(tj.read_text())
        data["master"]["tasks"] = []
        tj.write_text(json.dumps(data))
        r = self.p.check("--no-git")
        self.assertIn("secret", r.stdout)
        self.assertIn("no tasks yet", r.stdout)
        r2 = self.p.check("--no-git", "--allow-empty-plan")
        self.assertNotIn("ERROR tasks.json has no tasks", r2.stdout)

    def test_upgrade_replaces_owned_backs_up_and_keeps_seeded(self):
        d = self.p.dir
        nt = d / ".claude/skills/next-task/SKILL.md"
        nt.write_text(nt.read_text() + "\nlocal tweak\n")
        mem_before = (d / ".claude/rules/memory.md").read_text() + "\n- project fact\n"
        (d / ".claude/rules/memory.md").write_text(mem_before)
        (d / ".claude/HARNESS_VERSION").write_text("0.9.0\n")
        (d / ".claude/agents/reviewer.md").unlink()
        out = run([PY, str(ROOT / "scripts/apply_template.py"), "--target", str(d), "--upgrade"], ROOT).stdout
        self.assertNotIn("local tweak", nt.read_text())
        self.assertIn("local tweak", (d / ".harness-backup/0.9.0/.claude/skills/next-task/SKILL.md").read_text())
        self.assertEqual((d / ".claude/rules/memory.md").read_text(), mem_before)
        self.assertTrue((d / ".claude/agents/reviewer.md").exists())
        self.assertIn("0.9.0 ->", out)
        self.assertTrue((d / ".claude/skills/vps/SKILL.md").exists(), "library skills untouched")

    def test_upgrade_adds_vps_and_removes_blocking_ask_rules(self):
        d = self.p.dir
        shutil.rmtree(d / ".claude/skills/vps")
        s = json.loads((d / ".claude/settings.json").read_text())
        s["permissions"]["ask"] += ["Bash(ssh *)", "Bash(git push *)"]
        s["permissions"]["allow"] = [r for r in s["permissions"]["allow"] if "vps" not in r]
        (d / ".claude/settings.json").write_text(json.dumps(s))
        run([PY, str(ROOT / "scripts/apply_template.py"), "--target", str(d), "--upgrade",
             "--values", str(FIX / "values.json"), "--skills", "vps", "--settings", "vps"], ROOT)
        s = json.loads((d / ".claude/settings.json").read_text())
        self.assertIn("Bash(ssh vps *)", s["permissions"]["allow"])
        self.assertNotIn("Bash(ssh *)", s["permissions"]["ask"])
        self.assertNotIn("Bash(git push *)", s["permissions"]["ask"])
        self.assertIn("habit-dots", (d / ".claude/skills/vps/SKILL.md").read_text())


class OpenPermissions(unittest.TestCase):
    def setUp(self):
        # "open" is listed first on purpose: it must still be merged last
        self.p = Project(rules="", skills="", settings="open,python,node,vps")

    def tearDown(self):
        self.p.cleanup()

    def perms(self):
        return json.loads((self.p.dir / ".claude/settings.json").read_text())["permissions"]

    def test_open_allows_everything_but_keeps_safety_denies(self):
        p = self.perms()
        for rule in ("Bash", "Edit", "Write"):
            self.assertIn(rule, p["allow"])
        for rule in ("Bash(git push origin *)", "Bash(npm install *)", "Bash(pip install *)", "Bash(scp *)"):
            self.assertNotIn(rule, p["ask"], "ask beats allow: open must not leave this prompting")
        for rule in ("Bash(git push --force *)", "Bash(git reset --hard *)", "Read(./.env)", "Read(~/.ssh/**)"):
            self.assertIn(rule, p["deny"])
        self.assertIn("Bash(npx prisma migrate reset *)", p["ask"], "destructive DB reset still asks")

    def test_plain_upgrade_does_not_bring_the_asks_back(self):
        d = self.p.dir
        run([PY, str(ROOT / "scripts/apply_template.py"), "--target", str(d), "--upgrade",
             "--values", str(FIX / "values.json")], ROOT)
        p = self.perms()
        self.assertIn("Bash", p["allow"])
        self.assertNotIn("Bash(git push origin *)", p["ask"])
        self.assertIn("Bash(git push --force *)", p["deny"])


class TasksPy(unittest.TestCase):
    def setUp(self):
        self.p = Project(rules="", skills="", settings="")

    def tearDown(self):
        self.p.cleanup()

    def test_phase_listing_and_next(self):
        out = self.p.tasks("phase").stdout
        self.assertIn("phase 0 Foundation", out)
        self.assertIn("current phase: 0", out)
        self.assertIn("1 Scaffold", self.p.tasks("next").stdout)
        r = self.p.tasks("next", "--phase", "1", check=False)
        self.assertEqual(r.returncode, 1, "task 2 depends on 1, not done yet")

    def test_next_phase_after_done(self):
        self.p.tasks("set-status", "1", "done")
        self.assertIn("2 Habits", self.p.tasks("next", "--phase", "1").stdout)
        self.assertIn("current phase: 1", self.p.tasks("status").stdout)

    def test_human_flag_shown(self):
        out = self.p.tasks("phase", "3").stdout
        self.assertIn("[HUMAN]", out)
        self.assertIn("human-only: 5", out)
        self.assertIn("flags: human", self.p.tasks("show", "5").stdout)
        self.assertIn("HUMAN STEP", self.p.tasks("next", "--phase", "3").stdout)

    def test_validate_phase_rules(self):
        tj = self.p.dir / ".taskmaster/tasks/tasks.json"
        data = json.loads(tj.read_text())
        data["master"]["tasks"][1]["phase"] = 9
        data["master"]["tasks"][3]["phase"] = 0  # depends on task 3 in phase 1
        tj.write_text(json.dumps(data))
        out = self.p.tasks("validate", check=False).stdout
        self.assertIn("phase 9 is not in metadata.phases", out)
        self.assertIn("later phase", out)

    def test_add_defaults_phase_and_flags(self):
        self.p.tasks("add", "--title", "Backups", "--deps", "4", "--test", "ls backups", "--review")
        data = json.loads((self.p.dir / ".taskmaster/tasks/tasks.json").read_text())["master"]["tasks"]
        new = data[-1]
        self.assertEqual(new["phase"], 2)
        self.assertTrue(new["review"])
        self.assertIn("ok", self.p.tasks("validate").stdout)

    def test_render(self):
        md = (self.p.dir / "TASKS.md").read_text()
        self.assertIn("# Habit Dots task checklist", md)
        self.assertIn("## Phase 3 - Ship", md)
        self.assertIn("**[HUMAN]**", md)


class ScriptChecks(unittest.TestCase):
    """run_checks.py: free checks for runner: script tasks, no model."""

    def setUp(self):
        self.p = Project()
        d = self.p.dir
        (d / "checks").mkdir()
        (d / "checks/ok.py").write_text("print('all good')\n")
        (d / "checks/bad.py").write_text("import sys\nfor i in range(30): print('line', i)\nsys.exit(3)\n")
        (d / "frontend/mark.py").write_text("open('ran.txt', 'w').write('x')\n")
        self.exe = Path(PY).name.lower()
        for ext in (".exe", ".cmd", ".bat"):
            if self.exe.endswith(ext):
                self.exe = self.exe[: -len(ext)]
        cj = d / ".taskmaster/checks.json"
        cfg = json.loads(cj.read_text())
        cfg["allow"].append(self.exe)
        cj.write_text(json.dumps(cfg))

    def tearDown(self):
        self.p.cleanup()

    def edit(self, fn):
        tj = self.p.dir / ".taskmaster/tasks/tasks.json"
        data = json.loads(tj.read_text())
        fn(data["master"]["tasks"])
        tj.write_text(json.dumps(data))

    def add_script(self, tasks, tid, phase, deps, *cmds, status="pending"):
        tasks.append({"id": tid, "title": f"Gate {tid}", "status": status, "priority": "medium", "phase": phase,
                      "complexity": 2, "dependencies": deps, "runner": "script", "check": list(cmds),
                      "testStrategy": f"python .taskmaster/run_checks.py run --only {tid}", "subtasks": []})

    def checks(self, *args):
        return run([PY, ".taskmaster/run_checks.py", *args], self.p.dir, check=False)

    def status(self, tid):
        data = json.loads((self.p.dir / ".taskmaster/tasks/tasks.json").read_text())["master"]["tasks"]
        return next(t for t in data if t["id"] == tid)

    def test_validate_rejects_unknown_runner_and_missing_check(self):
        def f(t):
            t[0]["runner"] = "kernel"
            t[1]["runner"] = "script"
        self.edit(f)
        out = self.p.tasks("validate", check=False).stdout
        self.assertIn("runner 'kernel' must be one of", out)
        self.assertIn("2: runner is script but there is no check", out)

    def test_validate_rejects_shell_operators_strings_shells_and_inline_code(self):
        self.edit(lambda t: (self.add_script(t, 6, 0, [], ["pytest", "&&", "ruff"]),
                             self.add_script(t, 7, 0, [], "cd frontend && npm run build"),
                             self.add_script(t, 8, 0, [], ["bash", "-c", "pytest"]),
                             self.add_script(t, 9, 0, [], ["python", "-c", "print(1)"]),
                             self.add_script(t, 10, 0, [], {"cmd": ["pytest"], "cwd": "../elsewhere"})))
        out = self.p.tasks("validate", check=False).stdout
        self.assertIn("6: check: shell operator", out)
        self.assertIn("7: check: 'cd frontend && npm run build' is a string", out)
        self.assertIn("8: check: 'bash' is a shell", out)
        self.assertIn("9: check: inline code", out)
        self.assertIn("10: check: cwd '../elsewhere'", out)

    def test_plan_lists_open_script_tasks_in_dependency_order(self):
        def f(t):
            self.add_script(t, 6, 1, [], [PY, "checks/ok.py"])
            self.add_script(t, 7, 0, [], [PY, "checks/ok.py"], status="done")
            self.add_script(t, 8, 0, [1], [PY, "checks/ok.py"])
        self.edit(f)
        r = self.checks("plan")
        self.assertEqual(r.returncode, 0, r.stdout)
        lines = [ln for ln in r.stdout.splitlines() if not ln.startswith("  ")]
        self.assertEqual([ln.split()[0] for ln in lines], ["6", "8"], r.stdout)  # 7 done; 1-5 are agent tasks
        self.assertIn("8 Gate 8  [waiting on 1]", r.stdout)
        self.assertIn("6 Gate 6  [ready]", r.stdout)
        self.assertEqual(self.checks("plan", "--phase", "0").stdout.split()[0], "8")

    def test_run_marks_done_only_after_pass(self):
        self.edit(lambda t: self.add_script(t, 6, 0, [], [PY, "checks/ok.py"],
                                            {"cmd": [PY, "mark.py"], "cwd": "frontend"}))
        r = self.checks("run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS task 6", r.stdout)
        t = self.status(6)
        self.assertEqual(t["status"], "done")
        self.assertIn("script check passed: 2 command(s)", t["details"])
        self.assertTrue((self.p.dir / "frontend/ran.txt").exists(), "cwd is honoured")
        log = (self.p.dir / ".claude/tmp/checks/6.log").read_text()
        self.assertIn("stdout sha256", log)
        self.assertIn("result: PASS", log)

    def test_run_stops_at_first_failure_and_leaves_status(self):
        def f(t):
            self.add_script(t, 6, 0, [], [PY, "checks/bad.py"], [PY, "checks/ok.py"])
            self.add_script(t, 7, 0, [6], [PY, "checks/ok.py"])
        self.edit(f)
        r = self.checks("run")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL task 6", r.stdout)
        self.assertIn("exit 3, expected 0", r.stdout)
        self.assertIn("line 29", r.stdout)
        self.assertNotIn("line 9\n", r.stdout, "only the last 20 lines are printed")
        self.assertEqual(self.status(6)["status"], "pending")
        self.assertIn("script check FAILED", self.status(6)["details"])
        self.assertEqual(self.status(7)["status"], "pending")
        self.assertNotIn("PASS", r.stdout)

    def test_expected_exit_code(self):
        self.edit(lambda t: self.add_script(t, 6, 0, [], {"cmd": [PY, "checks/bad.py"], "expect": 3}))
        self.assertEqual(self.checks("run", "--only", "6").returncode, 0)
        self.assertEqual(self.status(6)["status"], "done")

    def test_commands_off_the_allowlist_are_refused(self):
        self.edit(lambda t: self.add_script(t, 6, 0, [], ["git", "push", "origin", "main"]))
        r = self.checks("run", "--only", "6")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not on the allowlist", r.stdout)
        self.assertEqual(self.status(6)["status"], "pending")
        self.assertIn("REFUSED", self.checks("plan").stdout)
        self.assertIn("script task check refused", self.p.check("--no-git").stdout)

    def test_shell_operator_refused_at_run_time_too(self):
        self.edit(lambda t: self.add_script(t, 6, 0, [], [PY, "checks/ok.py", ";", "rm", "-rf", "x"]))
        r = self.checks("run", "--only", "6")
        self.assertEqual(r.returncode, 2)
        self.assertIn("shell operator", r.stdout)

    def test_only_refuses_agent_tasks_and_waiting_tasks(self):
        self.edit(lambda t: self.add_script(t, 6, 0, [1], [PY, "checks/ok.py"]))
        self.assertEqual(self.checks("run", "--only", "1").returncode, 2)
        r = self.checks("run", "--only", "6")
        self.assertEqual(r.returncode, 2)
        self.assertIn("waiting on 1", r.stdout)
        self.assertIn("skipped: 6 (waiting on 1)", self.checks("run").stdout)

    def test_tasks_py_shows_script_tasks_and_add(self):
        self.p.tasks("add", "--title", "Phase 0 gate", "--phase", "0", "--runner", "script",
                     "--check", "ruff check .", "--check", "pytest -q")
        t = self.status(6)
        self.assertEqual(t["check"], [["ruff", "check", "."], ["pytest", "-q"]])
        self.assertEqual(t["testStrategy"], "python .taskmaster/run_checks.py run --only 6")
        self.assertIn("ok", self.p.tasks("validate").stdout)
        self.assertIn("runner: script", self.p.tasks("show", "6").stdout)
        self.assertIn("[SCRIPT]", self.p.tasks("phase", "0").stdout)
        self.p.tasks("set-status", "1", "done")
        self.assertIn("SCRIPT TASK", self.p.tasks("next", "--phase", "0").stdout)

    def test_no_bytecode_left_behind(self):
        self.checks("plan")
        self.assertFalse((self.p.dir / ".taskmaster/__pycache__").exists())

    def test_run_path_uses_stdlib_only(self):
        import ast
        src = (ROOT / "template/.taskmaster/run_checks.py").read_text(encoding="utf-8")
        mods = {n.names[0].name.split(".")[0] for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Import)}
        mods |= {n.module.split(".")[0] for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)}
        self.assertLessEqual(mods, {"argparse", "datetime", "hashlib", "json", "os", "shutil", "subprocess",
                                    "sys", "time", "pathlib", "tasks"})


class MergeGate(unittest.TestCase):
    """merge_gate.py decisions (offline: --ci and --files, so no GitHub calls)."""

    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.cleanup()

    def cfg(self, **kw):
        hj = self.p.dir / ".claude/harness.json"
        d = json.loads(hj.read_text())
        d.update(kw)
        hj.write_text(json.dumps(d))

    def gate(self, ci, files):
        return run([PY, ".claude/scripts/merge_gate.py", "--ci", ci, "--files", files], self.p.dir, check=False)

    def test_auto_merges_green_and_never_red_or_pending(self):
        r = self.gate("green", "app/page.tsx")
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (0, "DECISION=MERGE"))
        r = self.gate("red", "app/page.tsx")
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (1, "DECISION=FIX_CI"))
        r = self.gate("pending", "README.md")
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (4, "DECISION=CI_TIMEOUT"))
        self.assertEqual(self.gate("none", "app/page.tsx").returncode, 0, "no CI at all: verifier already ran tests")

    def test_owner_mode_never_merges(self):
        self.cfg(merge="owner")
        r = self.gate("green", "README.md")
        self.assertEqual(r.returncode, 3)
        self.assertIn("merge mode is owner", r.stdout)

    def test_safe_only(self):
        self.cfg(merge="safe-only")
        ok = "README.md,docs/setup.md,tests/test_x.py,src/a.test.ts,.taskmaster/tasks/tasks.json,TASKS.md," \
             ".claude/rules/memory.md,.taskmaster/docs/human-checklist.md"
        self.assertEqual(self.gate("green", ok).returncode, 0)
        for bad in ("app/api/checkout/route.ts", ".github/workflows/ci.yml", "package.json",
                    ".claude/skills/x/SKILL.md", "CLAUDE.md", "db/migrations/005.sql", ".taskmaster/tasks.py",
                    ".claude/rules/project.md"):
            r = self.gate("green", "README.md," + bad)
            self.assertEqual(r.returncode, 3, bad)
            self.assertIn(bad, r.stdout)

    def test_live_project_waits_for_queued_human_steps_and_eyes_on_checks(self):
        self.cfg(merge="auto", merge_deploys=True)
        self.assertEqual(self.gate("green", "app/page.tsx").returncode, 0)
        self.p.tasks("queue", "5")
        r = self.gate("green", "app/page.tsx")
        self.assertEqual(r.returncode, 3)
        self.assertIn("human step 5 Point a domain at the VPS isn't done", r.stdout)
        self.p.tasks("set-status", "5", "done")
        self.assertEqual(self.gate("green", "app/page.tsx").returncode, 0)
        mc = self.p.dir / ".taskmaster/docs/manual-checks.md"
        mc.write_text(mc.read_text() + "\n### Task 4 - Phone UI (2026-11-14)\n1. Open on a phone\n")
        r = self.gate("green", "app/page.tsx")
        self.assertEqual(r.returncode, 3)
        self.assertIn("eyes-on check", r.stdout)
        self.cfg(merge_deploys=False)
        self.assertEqual(self.gate("green", "app/page.tsx").returncode, 0, "not live: eyes-on doesn't block")

    def test_missing_or_bad_config_fails_closed(self):
        hj = self.p.dir / ".claude/harness.json"
        hj.write_text("{not json")
        self.assertEqual(self.gate("green", "README.md").returncode, 3)
        hj.unlink()
        r = self.gate("green", "README.md")
        self.assertEqual(r.returncode, 3)
        self.assertIn("no .claude/harness.json", r.stdout)

    def test_ci_state_reads_check_runs_and_commit_statuses(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("mg", ROOT / "template/.claude/scripts/merge_gate.py")
        mg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mg)
        ok = {"check_runs": [{"name": "test", "status": "completed", "conclusion": "success"}]}
        self.assertEqual(mg.ci_state(ok, {"statuses": []})[0], "green")
        self.assertEqual(mg.ci_state(ok, {"statuses": [{"context": "Vercel", "state": "failure"}]}),
                         ("red", ["Vercel"]))
        self.assertEqual(mg.ci_state(ok, {"statuses": [{"context": "Vercel", "state": "pending"}]})[0], "pending")
        self.assertEqual(mg.ci_state({"check_runs": []}, {"statuses": []})[0], "none")
        run_ = {"check_runs": [{"name": "e2e", "status": "in_progress", "conclusion": None}]}
        self.assertEqual(mg.ci_state(run_, {"statuses": []})[0], "pending")
        self.assertTrue(mg.is_safe(".claude/rules/memory.md", json.loads(
            (ROOT / "template/.claude/harness.json").read_text())))

    def test_checker_validates_harness_json(self):
        self.cfg(merge="yolo")
        self.assertIn("harness.json: merge must be", self.p.check("--no-git").stdout)
        self.cfg(merge="auto", merge_deploys=True)
        self.assertIn("every green PR goes live", self.p.check("--no-git").stdout)


class QueuedHumanSteps(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        tj = self.p.dir / ".taskmaster/tasks/tasks.json"
        data = json.loads(tj.read_text())
        t = data["master"]["tasks"]
        t[4]["phase"] = 2  # human DNS step in phase 2
        t.append({"id": 6, "title": "Deploy script", "status": "pending", "priority": "medium", "phase": 2,
                  "complexity": 3, "dependencies": [5], "details": "", "testStrategy": "bash deploy.sh --dry-run",
                  "subtasks": []})
        for x in t[:4]:
            x["status"] = "done"
        tj.write_text(json.dumps(data))

    def tearDown(self):
        self.p.cleanup()

    def test_queue_unblocks_dependents_but_keeps_the_step_open(self):
        self.assertIn("HUMAN STEP", self.p.tasks("next", "--phase", "2").stdout)
        self.p.tasks("queue", "5")
        self.assertIn("6 Deploy script", self.p.tasks("next", "--phase", "2").stdout)
        self.p.tasks("set-status", "6", "done")
        out = self.p.tasks("phase", "2").stdout
        self.assertIn("[QUEUED]", out)
        self.assertIn("agent work done: only queued human steps remain", out)
        self.assertEqual(self.p.tasks("next", "--phase", "2", check=False).returncode, 1)
        self.assertIn("current phase: None", self.p.tasks("phase").stdout, "queued steps do not hold a phase open")
        self.p.tasks("set-status", "5", "done")
        data = json.loads((self.p.dir / ".taskmaster/tasks/tasks.json").read_text())["master"]["tasks"]
        self.assertNotIn("queued", data[4])

    def test_only_human_tasks_can_be_queued(self):
        r = self.p.tasks("queue", "6", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a human task", r.stderr)


class ContextCheck(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("cc", ROOT / "template/.claude/scripts/context_check.py")
        self.cc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cc)
        self.base = Path(tempfile.mkdtemp(prefix="ctx-"))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def write(self, folder, name, tokens, age=0):
        d = self.base / folder
        d.mkdir(exist_ok=True)
        f = d / name
        f.write_text(json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": tokens}}}) + "\n")
        t = time.time() - age
        os.utime(f, (t, t))
        return f

    def test_only_this_project_and_the_larger_active_session(self):
        cwd = "/work/shop"
        enc = "-work-shop"
        self.write("-work-other", "x.jsonl", 999999)
        self.assertEqual(self.cc.transcripts(self.base, cwd), [], "never reads another project's transcripts")
        self.write(enc, "a.jsonl", 40000)
        self.write(enc, "b.jsonl", 120000, age=60)
        self.write(enc, "old.jsonl", 900000, age=3600)
        got = self.cc.transcripts(self.base, cwd)
        self.assertEqual(sorted(f.name for f in got), ["a.jsonl", "b.jsonl"])
        self.assertEqual(max(self.cc.last_usage(f) for f in got), 120000)


class HarnessCommand(unittest.TestCase):
    def test_user_skill_is_valid(self):
        text = (ROOT / "user-skill/harness/SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: harness\n"))
        self.assertIn("disable-model-invocation: true", text)
        self.assertIn("BOOTSTRAP.md", text)
        self.assertIn("UPGRADE.md", text)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("raw.githubusercontent.com/jenozu/master-harness/main/user-skill/harness/SKILL.md", readme)


class LineEndings(unittest.TestCase):
    """Harness files are written and committed with LF, also on Windows."""

    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.cleanup()

    def test_scripts_write_lf(self):
        self.p.tasks("set-status", "1", "done")
        run([PY, ".taskmaster/render_tasks_md.py"], self.p.dir)
        for rel in (".taskmaster/tasks/tasks.json", "TASKS.md", ".claude/HARNESS_VERSION", ".claude/harness.json",
                    ".taskmaster/checks.json", ".claude/settings.json", "CLAUDE.md", ".gitattributes"):
            self.assertNotIn(b"\r\n", (self.p.dir / rel).read_bytes(), rel)

    def test_gitattributes_added_once(self):
        ga = (self.p.dir / ".gitattributes").read_text()
        self.assertIn(".taskmaster/** text=auto eol=lf", ga)
        run([PY, str(ROOT / "scripts/apply_template.py"), "--target", str(self.p.dir), "--upgrade"], self.p.dir)
        self.assertEqual((self.p.dir / ".gitattributes").read_text().count("eol=lf"), ga.count("eol=lf"))

    @unittest.skipIf(sys.platform == "win32", "Git for Windows converts the staged fixture; the check itself only "
                     "reads the index (git ls-files --eol), which is the same on every OS")
    def test_checker_flags_crlf_committed(self):
        d = self.p.dir
        git = ["git", "-c", "core.autocrlf=false", "-c", "user.name=t", "-c", "user.email=t@t"]
        (d / ".gitattributes").unlink()
        run(git + ["commit", "-q", "-am", "no attributes"], d)  # git reads .gitattributes from the index too
        tj = d / ".taskmaster/tasks/tasks.json"
        tj.write_bytes(tj.read_bytes().replace(b"\n", b"\r\n"))
        run(git + ["add", "-A"], d)
        run(git + ["commit", "-q", "-m", "crlf"], d)
        out = self.p.check().stdout
        self.assertIn("Windows line endings", out)
        self.assertIn(".taskmaster/tasks/tasks.json", out)


class CheapUpgrade(unittest.TestCase):
    """Upgrades list only files edited in the project, and print the changelog's project actions."""

    def setUp(self):
        self.p = Project()
        self.old = Path(tempfile.mkdtemp(prefix="oldtpl-"))
        shutil.copytree(ROOT / "template", self.old, dirs_exist_ok=True)
        # Pretend the harness changed two owned files since the old version, and the project is on that old version.
        for rel in (".claude/agents/verifier.md", ".claude/skills/status/SKILL.md"):
            older = (self.old / rel).read_text(encoding="utf-8") + "\nold line\n"
            (self.old / rel).write_text(older, encoding="utf-8", newline="\n")
            (self.p.dir / rel).write_text(older, encoding="utf-8", newline="\n")
        (self.p.dir / ".claude/HARNESS_VERSION").write_text("1.5.0\n")

    def tearDown(self):
        self.p.cleanup()
        shutil.rmtree(self.old, ignore_errors=True)

    def upgrade(self, *extra):
        return run([PY, str(ROOT / "scripts/apply_template.py"), "--target", str(self.p.dir), "--upgrade", *extra],
                   self.p.dir).stdout

    def test_untouched_files_need_no_review(self):
        out = self.upgrade("--old-template", str(self.old))
        self.assertIn("replaced, untouched since the old version: 2", out)
        self.assertIn("CUSTOMIZED: none (nothing to review)", out)
        self.assertFalse((self.p.dir / ".harness-backup").exists(), "nothing to back up")

    def test_edited_file_is_listed_and_backed_up(self):
        (self.p.dir / ".claude/agents/verifier.md").write_text("project edit\n", encoding="utf-8")
        out = self.upgrade("--old-template", str(self.old))
        self.assertIn("CUSTOMIZED (edited in this project", out)
        self.assertIn("  .claude/agents/verifier.md", out.split("CUSTOMIZED")[1])
        self.assertNotIn(".claude/skills/status/SKILL.md", out.split("CUSTOMIZED")[1].split("note:")[0])
        self.assertEqual((self.p.dir / ".harness-backup/1.5.0/.claude/agents/verifier.md").read_text(),
                         "project edit\n")

    def test_crlf_copy_of_an_untouched_file_counts_as_untouched(self):
        f = self.p.dir / ".claude/agents/verifier.md"
        f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
        self.assertIn("CUSTOMIZED: none", self.upgrade("--old-template", str(self.old)))

    def test_project_actions_since_old_version_only(self):
        out = self.upgrade("--old-template", str(self.old))
        actions = out.split("PROJECT ACTIONS")[1]
        self.assertIn("[2.0.0] Project action", actions)
        self.assertIn("[2.0.1] Project action", actions)
        self.assertNotIn("[1.5.0]", actions)
        self.assertLess(actions.index("[2.0.0]"), actions.index("[2.0.1]"), "oldest first")
        (self.p.dir / ".claude/HARNESS_VERSION").write_text((ROOT / "VERSION").read_text())
        self.assertIn("PROJECT ACTIONS: none", self.upgrade())

    @unittest.skipIf(subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"],
                                    capture_output=True, text=True).stdout.strip() != "false", "shallow clone")
    def test_old_template_from_git_history(self):
        old = subprocess.run(["git", "-C", str(ROOT), "show", "43db62f:template/.claude/agents/phase-runner.md"],
                             capture_output=True, text=True, encoding="utf-8")
        if old.returncode != 0:
            self.skipTest("v1.5.0 commit not in this clone")
        (self.p.dir / ".claude/agents/phase-runner.md").write_text(old.stdout, encoding="utf-8", newline="\n")
        out = self.upgrade()
        self.assertNotIn("couldn't find the v1.5.0 template", out)
        self.assertIn(".claude/agents/phase-runner.md", out.split("CUSTOMIZED")[0])  # listed as untouched


class DevServer(unittest.TestCase):
    def test_start_status_stop(self):
        p = Project(rules="", skills="", settings="")
        try:
            cfg = [{"name": "web", "cwd": ".", "cmd": f'"{PY}" -m http.server 8799', "health": "http://localhost:8799/"}]
            (p.dir / ".claude/dev-servers.json").write_text(json.dumps(cfg))
            ds = [PY, ".claude/scripts/devserver.py"]
            self.assertIn("up at", run(ds + ["start", "web"], p.dir).stdout)
            self.assertIn("started by devserver.py", run(ds + ["status"], p.dir).stdout)
            self.assertIn("stopped", run(ds + ["stop", "web"], p.dir).stdout)
        finally:
            run([PY, ".claude/scripts/devserver.py", "stop", "all"], p.dir, check=False)
            p.cleanup()


AGENT = ROOT / "library/vps-kit/server/vps-agent"
NO_BASH = os.name == "nt" or not shutil.which("bash")


@unittest.skipIf(NO_BASH, "vps-agent runs on Linux servers")
class VpsAgent(unittest.TestCase):
    def ssh(self, command):
        env = dict(os.environ, VPS_AGENT_TEST="1", SSH_ORIGINAL_COMMAND=command)
        r = subprocess.run(["bash", str(AGENT), "--ssh"], capture_output=True, text=True, env=env)
        return (r.stdout + r.stderr).strip()

    def test_allowed_commands_go_through_sudo(self):
        for cmd in ("status myapp", "deploy my-app abc1234", "env-set myapp FOO=bar", "logs myapp -n 20",
                    "create myapp --db --ext pg_trgm,unaccent", "backup myapp", "tls myapp", "rollback myapp"):
            self.assertIn(f"EXEC sudo -n /usr/local/sbin/vps-agent {cmd}", self.ssh(cmd), cmd)

    def test_everything_else_is_refused(self):
        for cmd in ("restore myapp /x.dump", "destroy myapp --yes", "bash", "cat /etc/shadow",
                    "status myapp; rm -rf /", "status myapp && id", "logs $(whoami)", "logs `id`",
                    "env-set myapp A='x y'", "status myapp | sh", "status myapp\nid",
                    "git-upload-pack '/srv/git/myapp.git'", "git-receive-pack '/etc/passwd'",
                    "git-receive-pack '/srv/git/../../etc.git'"):
            out = self.ssh(cmd)
            self.assertNotIn("EXEC", out, cmd)
            self.assertIn("ERROR", out, cmd)

    def test_app_names_validated(self):
        # the filter passes plain tokens; every root subcommand then validates the app name
        script = AGENT.read_text()
        import re
        name_re = re.search(r"NAME_RE='([^']+)'", script).group(1)
        for bad in ("../etc", "My_App", "a", "-x", "x" * 40, "app;id"):
            self.assertIsNone(re.match(name_re, bad), bad)
        self.assertIsNotNone(re.match(name_re, "habit-dots"))
        self.assertIn('need_app "$name"', script)

    def test_git_push_path(self):
        self.assertIn("no git repo for 'myapp'", self.ssh("git-receive-pack '/srv/git/myapp.git'"))
        self.assertIn("no git repo for 'myapp'", self.ssh("git-receive-pack 'myapp.git'"))

    def test_empty_command_shows_help(self):
        self.assertIn("deploy gatekeeper", self.ssh(""))

    def render(self, cfg):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
        env = dict(os.environ, VPS_AGENT_TEST="1")
        r = subprocess.run(["bash", str(AGENT), "_render-locations", "demo", "8101", f.name, "x"],
                           capture_output=True, text=True, env=env)
        os.unlink(f.name)
        return r.stdout + r.stderr

    def test_nginx_rendering(self):
        full = self.render({"web": {"dir": "frontend", "out": "dist"},
                            "api": {"dir": "backend", "runtime": "python", "start": "x"}})
        self.assertIn("location /api/ {", full)
        self.assertIn("proxy_pass http://127.0.0.1:8101/;", full)
        self.assertIn("root /srv/apps/demo/current/frontend/dist;", full)
        nxt = self.render({"api": {"runtime": "node", "start": "npm start"}})
        self.assertIn("location / {", nxt)
        self.assertIn("proxy_pass http://127.0.0.1:8101;", nxt)
        self.assertNotIn("root ", nxt)
        bad = self.render({"web": {"dir": "x;rm", "out": "dist"}})
        self.assertIn("ERROR", bad)

    def agent_cmd(self, *args, conf):
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write(conf)
        env = dict(os.environ, VPS_AGENT_TEST="1", VPS_AGENT_CONF=f.name)
        r = subprocess.run(["bash", str(AGENT), *args], capture_output=True, text=True, env=env)
        os.unlink(f.name)
        return r.stdout + r.stderr

    TRAEFIK_CONF = ("EDGE=traefik\nTRAEFIK_DIR=/docker/traefik/dynamic\nTRAEFIK_RESOLVER=letsencrypt\n"
                    "TRAEFIK_ENTRYPOINT=websecure\n")

    def test_traefik_mode_rendering(self):
        site = self.agent_cmd("_render-site", "demo", "demo.example.com", "8500", conf=self.TRAEFIK_CONF)
        self.assertIn("listen 127.0.0.1:8500;", site)
        self.assertNotIn("listen 80", site)
        self.assertNotIn("[::]", site)
        tf = self.agent_cmd("_render-traefik", "demo", "demo.example.com", "8500", conf=self.TRAEFIK_CONF)
        self.assertIn("rule: \"Host(`demo.example.com`)\"", tf)
        self.assertIn("- websecure", tf)
        self.assertIn("certResolver: letsencrypt", tf)
        self.assertIn('url: "http://127.0.0.1:8500"', tf)
        # behind Traefik the client's scheme/IP come from Traefik's headers, not from the local hop
        cfg = {"api": {"runtime": "node", "start": "npm start"}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
        loc = self.agent_cmd("_render-locations", "demo", "8101", f.name, "x", conf=self.TRAEFIK_CONF)
        os.unlink(f.name)
        self.assertIn("X-Forwarded-Proto https;", loc)
        self.assertIn("X-Real-IP $http_x_real_ip;", loc)

    def test_nginx_mode_still_listens_on_80(self):
        site = self.agent_cmd("_render-site", "demo", "demo.example.com", conf="EDGE=nginx\n")
        self.assertIn("listen 80;", site)

    def test_bootstrap_detects_traefik(self):
        if not shutil.which("jq"):
            self.skipTest("jq not installed")
        bootstrap = ROOT / "library/vps-kit/server/bootstrap.sh"
        with tempfile.TemporaryDirectory() as t:
            dyn = Path(t) / "dynamic"
            dyn.mkdir()
            insp = [{"Args": ["--providers.file.directory=/etc/traefik/dynamic", "--providers.docker=true",
                              "--entrypoints.web.address=:80", "--entrypoints.websecure.address=:443",
                              "--certificatesresolvers.letsencrypt.acme.httpchallenge=true",
                              "--certificatesresolvers.letsencrypt.acme.email=a@b.c"],
                     "Mounts": [{"Source": str(dyn), "Destination": "/etc/traefik/dynamic"},
                                {"Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock"}]}]
            (Path(t) / "insp.json").write_text(json.dumps(insp))
            (Path(t) / "docker").write_text(
                '#!/bin/sh\ncase "$1" in\n ps) echo "rf-scanner-api-1 rf-scanner-api"; echo "traefik-traefik-1 traefik:latest";;\n'
                f' inspect) cat "{t}/insp.json";;\nesac\n')
            (Path(t) / "docker").chmod(0o755)
            (Path(t) / "k.pub").write_text("ssh-ed25519 AAAA test\n")
            env = dict(os.environ, VPS_BOOTSTRAP_TEST="1", PATH=f"{t}:{os.environ['PATH']}")
            args = ["bash", str(bootstrap), "--pubkey-file", str(Path(t) / "k.pub"), "--email", "a@b.c"]
            out = subprocess.run(args, capture_output=True, text=True, env=env).stdout
            self.assertIn("EDGE=traefik", out)
            self.assertIn(f"TRAEFIK_DIR={dyn}", out)
            self.assertIn("TRAEFIK_RESOLVER=letsencrypt", out)
            self.assertIn("TRAEFIK_ENTRYPOINT=websecure", out)
            # without docker/Traefik the classic nginx setup is kept
            (Path(t) / "docker").write_text('#!/bin/sh\nexit 0\n')
            out = subprocess.run(args, capture_output=True, text=True, env=env).stdout
            self.assertIn("EDGE=nginx", out)

    def test_kit_scripts_have_lf_line_endings(self):
        for f in ("server/vps-agent", "server/bootstrap.sh", "setup_vps.sh"):
            self.assertNotIn(b"\r", (ROOT / "library/vps-kit" / f).read_bytes(), f)

    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck not installed")
    def test_shellcheck(self):
        kit = ROOT / "library/vps-kit"
        r = subprocess.run(["shellcheck", "-S", "warning", str(AGENT), str(kit / "server/bootstrap.sh"),
                            str(kit / "setup_vps.sh")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
