# VPS kit: let every project deploy to your VPS without you

After a one-time setup, any project built with master-harness can create its app on your VPS, deploy with
`git push vps main`, and check logs, all without you stepping in. The server enforces what agents can do.

## How it's kept safe
- Claude gets **its own key** (`~/.ssh/claude_vps`), separate from yours.
- On the server, that key logs in as a `deploy` user and can **only run `vps-agent`**. The SSH forced command
  rejects everything else: no shell, no `rm`, no reading files.
- `vps-agent` allows: create, deploy, status, logs, env-keys/env-set (values are never shown), backups, tls,
  rollback. **Restore and destroy are admin-only**: you run them with sudo from your own login.
- Each app runs as its own unprivileged user with its own database and password. Build commands from a repo run
  as that user, never as root.
- Deploys health-check the new version and **roll back automatically** if it doesn't come up.
- Databases are backed up nightly (kept 14 days), and before every restore.

## One-time setup (about 5 minutes)
You need: the VPS's IP, an admin login (root or a sudo user) that works from your PC, and an email address for
HTTPS certificates. Optional but recommended: a domain you control.

1. In Git Bash on your PC:
   ```
   git clone https://github.com/jenozu/master-harness ~/master-harness
   bash ~/master-harness/library/vps-kit/setup_vps.sh root@YOUR_VPS_IP you@example.com apps.yourdomain.com
   ```
   Use your own admin login in place of `root@...`. Leave off the last argument if you don't want a shared apps domain.
2. If you gave an apps domain: in your DNS provider, add **one** record:
   `A   *.apps.yourdomain.com   →   YOUR_VPS_IP`. From then on every new app gets
   `https://<app>.apps.yourdomain.com` with no DNS work at all.
3. Done. Check with `ssh vps list`.

**Servers that already run Traefik** (for example with other Docker apps): the setup detects it and uses it.
Traefik keeps ports 80/443 and issues the HTTPS certificates; each app gets one small file in Traefik's config
folder, and nginx only runs privately on `127.0.0.1`. Nothing else on the server is touched. No flags needed;
force a mode with `--edge nginx` or `--edge traefik` on `bootstrap.sh` if detection ever picks wrong.

Re-run the same command any time to update `vps-agent` after master-harness changes. It's additive: existing
sites, databases and apps (FitTrack+ included) aren't touched.

## What projects do with it
BOOTSTRAP sees `~/.claude/vps.json`, installs the `vps` skill and its permissions, and plans the Ship phase as
agent tasks: create the app, write `deploy/vps.json`, deploy, smoke test. The only human tasks left are things
like API keys you have to supply.

## Admin commands (on the server, as you)
```
sudo vps-agent list
sudo vps-agent backups <app>
sudo vps-agent restore <app> /var/backups/apps/<app>/<file>.dump
sudo vps-agent destroy <app> --yes [--drop-db]
sudo cat /srv/apps/<app>/shared/.env            # see or edit an app's secrets
```

## Revoke Claude's access
On the server: `sudo rm /home/deploy/.ssh/authorized_keys`. On your PC: delete `~/.ssh/claude_vps*`, the
`master-harness vps` block in `~/.ssh/config`, and `~/.claude/vps.json`.
