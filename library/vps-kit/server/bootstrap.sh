#!/usr/bin/env bash
# One-time VPS setup for the master-harness VPS kit. Normally run for you by setup_vps.sh from your PC.
# Safe to re-run and additive: it never removes existing nginx sites, databases, users or apps
# (an existing app like FitTrack+ keeps running untouched).
#
#   sudo bash bootstrap.sh --pubkey-file claude_vps.pub --email you@example.com [--apps-domain apps.example.com]
#
# What it does: installs packages (git, jq, nginx, certbot, PostgreSQL, Python venv, Node 22, ufw), adds swap on
# small servers, creates the "deploy" user whose SSH key can ONLY run vps-agent (forced command), installs
# vps-agent and its sudo rule, opens ports 22/80/443, schedules nightly database backups.
set -euo pipefail

PUBKEY_FILE="" EMAIL="" APPS_DOMAIN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pubkey-file) PUBKEY_FILE="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --apps-domain) APPS_DOMAIN="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
[[ -f "$PUBKEY_FILE" ]] || { echo "--pubkey-file is required (the Claude key's .pub file)" >&2; exit 2; }
[[ -n "$EMAIL" ]] || { echo "--email is required (HTTPS certificate notices)" >&2; exit 2; }
grep -qE '^ssh-(ed25519|rsa) ' "$PUBKEY_FILE" || { echo "$PUBKEY_FILE doesn't look like an SSH public key" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
[[ -f "$HERE/vps-agent" ]] || { echo "vps-agent must be next to bootstrap.sh" >&2; exit 2; }
. /etc/os-release
[[ "$ID" == "ubuntu" || "$ID" == "debian" ]] || echo "Warning: written for Ubuntu/Debian, found $ID. Continuing."

say() { echo; echo "==> $*"; }

say "Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git jq curl ca-certificates openssl build-essential \
  nginx certbot python3-certbot-nginx postgresql postgresql-contrib \
  python3 python3-venv python3-dev libpq-dev ufw
if ! command -v node >/dev/null || [[ "$(node -v | sed 's/v\([0-9]*\).*/\1/')" -lt 20 ]]; then
  say "Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y -q nodejs
fi
systemctl enable --now postgresql nginx >/dev/null

MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [[ $MEM_MB -lt 3000 ]] && ! swapon --show | grep -q .; then
  say "2 GB swap file (${MEM_MB} MB RAM: builds can run out of memory)"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

say "vps-agent"
install -o root -g root -m 755 "$HERE/vps-agent" /usr/local/sbin/vps-agent
mkdir -p /etc/vps-agent /srv/apps /srv/git /var/backups/apps /etc/nginx/vps-apps
chmod 755 /srv/apps
{
  echo "# vps-agent settings (edit by hand if needed)"
  echo "EMAIL=$EMAIL"
  echo "APPS_DOMAIN=$APPS_DOMAIN"
} > /etc/vps-agent/config

say "deploy user (SSH key restricted to vps-agent)"
id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
passwd -l deploy >/dev/null 2>&1 || true
chown deploy:deploy /srv/git
install -d -o deploy -g deploy -m 700 /home/deploy/.ssh
KEY="$(head -1 "$PUBKEY_FILE")"
AUTH=/home/deploy/.ssh/authorized_keys
touch "$AUTH"
grep -vF "$(echo "$KEY" | awk '{print $2}')" "$AUTH" > "$AUTH.tmp" || true
echo "restrict,command=\"/usr/local/sbin/vps-agent --ssh\" $KEY" >> "$AUTH.tmp"
mv "$AUTH.tmp" "$AUTH"
chown deploy:deploy "$AUTH"; chmod 600 "$AUTH"

SUDOERS=/etc/sudoers.d/vps-agent
echo "deploy ALL=(root) NOPASSWD: /usr/local/sbin/vps-agent" > "$SUDOERS.tmp"
chmod 440 "$SUDOERS.tmp"
visudo -cf "$SUDOERS.tmp" >/dev/null && mv "$SUDOERS.tmp" "$SUDOERS"

say "Firewall (22, 80, 443)"
ufw allow OpenSSH >/dev/null
ufw allow 'Nginx Full' >/dev/null
ufw --force enable >/dev/null

say "Nightly database backups (03:15, kept 14 days)"
echo "15 3 * * * root /usr/local/sbin/vps-agent backup --all >> /var/log/vps-agent-backup.log 2>&1" > /etc/cron.d/vps-agent

say "Done"
echo "vps-agent $(/usr/local/sbin/vps-agent version | awk '{print $2}') installed. Existing sites and apps were not touched."
[[ -n "$APPS_DOMAIN" ]] && echo "New apps default to <app>.$APPS_DOMAIN. Point a wildcard DNS record *.$APPS_DOMAIN at this server."
exit 0
