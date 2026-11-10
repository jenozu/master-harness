"""Tests for tasks.py, apply_template.py and check_harness.py (stdlib unittest).

Run from the repo root:  python -m unittest discover -s tests -q
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
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
