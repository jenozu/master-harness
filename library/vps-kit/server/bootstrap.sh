#!/usr/bin/env bash
# One-time VPS setup for the master-harness VPS kit. Normally run for you by setup_vps.sh from your PC.
# Safe to re-run and additive: it never removes existing nginx sites, databases, users or apps
# (an existing app like FitTrack+ keeps running untouched).
#
#   sudo bash bootstrap.sh --pubkey-file claude_vps.pub --email you@example.com [--apps-domain apps.example.com]
#                          [--edge auto|nginx|traefik]
#
# What it does: installs packages (git, jq, nginx, certbot, PostgreSQL, Python venv, Node 22, ufw), adds swap on
# small servers, creates the "deploy" user whose SSH key can ONLY run vps-agent (forced command), installs
# vps-agent and its sudo rule, opens ports 22/80/443, schedules nightly database backups.
#
# Edge: if Traefik already owns ports 80/443 (a Docker container), --edge auto (the default) switches to Traefik
# mode: nginx only listens on 127.0.0.1, certbot isn't installed, and each app gets one file in Traefik's dynamic
# config folder. Otherwise nginx owns 80/443 and certbot issues certificates.
set -euo pipefail

PUBKEY_FILE="" EMAIL="" APPS_DOMAIN="" EDGE_OPT="auto"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pubkey-file) PUBKEY_FILE="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --apps-domain) APPS_DOMAIN="$2"; shift 2 ;;
    --edge) EDGE_OPT="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 || -n "${VPS_BOOTSTRAP_TEST:-}" ]] || { echo "Run with sudo." >&2; exit 1; }
[[ -f "$PUBKEY_FILE" ]] || { echo "--pubkey-file is required (the Claude key's .pub file)" >&2; exit 2; }
[[ -n "$EMAIL" ]] || { echo "--email is required (HTTPS certificate notices)" >&2; exit 2; }
grep -qE '^ssh-(ed25519|rsa) ' "$PUBKEY_FILE" || { echo "$PUBKEY_FILE doesn't look like an SSH public key" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
[[ -f "$HERE/vps-agent" ]] || { echo "vps-agent must be next to bootstrap.sh" >&2; exit 2; }
. /etc/os-release
[[ "$ID" == "ubuntu" || "$ID" == "debian" ]] || echo "Warning: written for Ubuntu/Debian, found $ID. Continuing."

say() { echo; echo "==> $*"; }

[[ "$EDGE_OPT" =~ ^(auto|nginx|traefik)$ ]] || { echo "--edge must be auto, nginx or traefik" >&2; exit 2; }

# ---- who owns ports 80/443? (Traefik in Docker, from its own container settings) ----
EDGE=nginx TRAEFIK_DIR="" TRAEFIK_RESOLVER="" TRAEFIK_ENTRYPOINT=""
detect_traefik() {
  command -v docker >/dev/null || return 1
  local c insp args dyn
  c="$(docker ps --format '{{.Names}} {{.Image}}' 2>/dev/null | awk 'tolower($0) ~ /traefik/ {print $1; exit}')"
  [[ -n "$c" ]] || return 1
  command -v jq >/dev/null || apt-get install -y -q jq >/dev/null
  insp="$(docker inspect "$c")"
  args="$(jq -r '.[0].Args[]?' <<< "$insp")"
  dyn="$(sed -n 's/^--providers\.file\.directory=//p' <<< "$args" | head -1)"
  [[ -n "$dyn" ]] || { echo "Traefik found but its file provider isn't enabled (no --providers.file.directory)." >&2; return 1; }
  TRAEFIK_DIR="$(jq -r --arg d "$dyn" '.[0].Mounts[]? | select(.Destination==$d) | .Source' <<< "$insp" | head -1)"
  [[ -n "$TRAEFIK_DIR" && -d "$TRAEFIK_DIR" ]] || { echo "Traefik's config folder $dyn isn't a mounted folder on this server." >&2; return 1; }
  TRAEFIK_RESOLVER="$(sed -n 's/^--certificatesresolvers\.\([^.]*\)\.acme.*/\1/p' <<< "$args" | head -1)"
  TRAEFIK_ENTRYPOINT="$(sed -n 's/^--entrypoints\.\([^.]*\)\.address=:443$/\1/p' <<< "$args" | head -1)"
  [[ -n "$TRAEFIK_RESOLVER" && -n "$TRAEFIK_ENTRYPOINT" ]] || { echo "Traefik has no HTTPS entrypoint or certificate resolver in its settings." >&2; return 1; }
  return 0
}
case "$EDGE_OPT" in
  traefik) detect_traefik || { echo "--edge traefik was requested but Traefik couldn't be set up (see above)." >&2; exit 1; }; EDGE=traefik ;;
  auto)    detect_traefik && EDGE=traefik || true ;;
esac
if [[ "$EDGE" == traefik ]]; then
  echo "Traefik detected: apps will be published through it (config folder $TRAEFIK_DIR, certificate resolver '$TRAEFIK_RESOLVER')."
fi

if [[ -n "${VPS_BOOTSTRAP_TEST:-}" ]]; then  # tests only: report what was detected, change nothing
  echo "EDGE=$EDGE"; echo "TRAEFIK_DIR=$TRAEFIK_DIR"; echo "TRAEFIK_RESOLVER=$TRAEFIK_RESOLVER"
  echo "TRAEFIK_ENTRYPOINT=$TRAEFIK_ENTRYPOINT"; exit 0
fi

say "Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
PKGS="git jq curl ca-certificates openssl build-essential nginx postgresql postgresql-contrib \
  python3 python3-venv python3-dev libpq-dev ufw"
[[ "$EDGE" == traefik ]] || PKGS="$PKGS certbot python3-certbot-nginx"
# shellcheck disable=SC2086
apt-get install -y -q $PKGS
if ! command -v node >/dev/null || [[ "$(node -v | sed 's/v\([0-9]*\).*/\1/')" -lt 20 ]]; then
  say "Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y -q nodejs
fi
systemctl enable --now postgresql >/dev/null
if [[ "$EDGE" == traefik ]]; then
  # nginx must never grab ports 80/443 here: drop the stock site; apps listen on 127.0.0.1 only
  rm -f /etc/nginx/sites-enabled/default
  systemctl enable nginx >/dev/null 2>&1 || true
  systemctl reset-failed nginx 2>/dev/null || true
  nginx -t >/dev/null 2>&1 && { systemctl restart nginx || true; }
else
  systemctl enable --now nginx >/dev/null
fi

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
  echo "EDGE=$EDGE"
  if [[ "$EDGE" == traefik ]]; then
    echo "TRAEFIK_DIR=$TRAEFIK_DIR"
    echo "TRAEFIK_RESOLVER=$TRAEFIK_RESOLVER"
    echo "TRAEFIK_ENTRYPOINT=$TRAEFIK_ENTRYPOINT"
  fi
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
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

say "Nightly database backups (03:15, kept 14 days)"
echo "15 3 * * * root /usr/local/sbin/vps-agent backup --all >> /var/log/vps-agent-backup.log 2>&1" > /etc/cron.d/vps-agent

say "Done"
echo "vps-agent $(/usr/local/sbin/vps-agent version | awk '{print $2}') installed. Existing sites and apps were not touched."
echo "Web edge: $EDGE"
[[ -n "$APPS_DOMAIN" ]] && echo "New apps default to <app>.$APPS_DOMAIN. Point a wildcard DNS record *.$APPS_DOMAIN at this server."
exit 0
