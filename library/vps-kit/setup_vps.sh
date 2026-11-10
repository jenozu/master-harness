#!/usr/bin/env bash
# One-time: connect Claude Code on this computer to your VPS. Run it yourself in a terminal (Git Bash on Windows),
# because it logs in with YOUR admin account and may ask for your password.
#
#   bash setup_vps.sh <admin-ssh-target> <email> [apps-domain]
#   bash setup_vps.sh root@203.0.113.10 you@example.com apps.example.com
#
# It: creates a dedicated key (~/.ssh/claude_vps), copies the kit to the server and runs bootstrap.sh there with
# your admin login, adds a "vps" host alias to ~/.ssh/config (user deploy, the new key), records the setup in
# ~/.claude/vps.json so new projects know the VPS exists, and tests the connection.
# Safe to re-run (e.g. after updating master-harness, to install a newer vps-agent).
set -euo pipefail

ADMIN="${1:-}" EMAIL="${2:-}" APPS_DOMAIN="${3:-}"
if [[ -z "$ADMIN" || -z "$EMAIL" ]]; then
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${ADMIN#*@}"
HOST="${HOST%%:*}"
KEY="$HOME/.ssh/claude_vps"
SSHCONF="$HOME/.ssh/config"

say() { echo; echo "==> $*"; }

say "Key for Claude: $KEY"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
if [[ ! -f "$KEY" ]]; then
  ssh-keygen -q -t ed25519 -N "" -C "claude-vps@$(hostname)" -f "$KEY"
  echo "created"
else
  echo "already exists, reusing it"
fi

say "Installing the kit on $HOST (as $ADMIN; you may be asked for your password)"
REMOTE_DIR="/tmp/vps-kit-$$"
ssh "$ADMIN" "mkdir -p $REMOTE_DIR"
# Git on Windows can turn line endings into CRLF, which Linux can't run: copy LF-only versions.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
for f in bootstrap.sh vps-agent; do tr -d '\r' < "$HERE/server/$f" > "$STAGE/$f"; done
cp "$KEY.pub" "$STAGE/claude_vps.pub"
scp -q "$STAGE/bootstrap.sh" "$STAGE/vps-agent" "$STAGE/claude_vps.pub" "$ADMIN:$REMOTE_DIR/"
ssh -t "$ADMIN" "cd $REMOTE_DIR && if [ \"\$(id -u)\" = 0 ]; then S=; else S=sudo; fi; \
  \$S bash bootstrap.sh --pubkey-file claude_vps.pub --email '$EMAIL' --apps-domain '$APPS_DOMAIN'; rc=\$?; \
  rm -rf $REMOTE_DIR; exit \$rc"

say "SSH alias 'vps' in $SSHCONF"
touch "$SSHCONF" && chmod 600 "$SSHCONF"
BLOCK="# >>> master-harness vps >>>
Host vps
    HostName $HOST
    User deploy
    IdentityFile $KEY
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
    ServerAliveInterval 30
# <<< master-harness vps <<<"
awk '/^# >>> master-harness vps >>>/{skip=1} !skip{print} /^# <<< master-harness vps <<</{skip=0}' "$SSHCONF" > "$SSHCONF.tmp"
{ printf '%s\n\n' "$BLOCK"; cat "$SSHCONF.tmp"; } > "$SSHCONF"
rm -f "$SSHCONF.tmp"

say "Recording the setup in ~/.claude/vps.json"
mkdir -p "$HOME/.claude"
cat > "$HOME/.claude/vps.json" <<EOF
{
  "host_alias": "vps",
  "host": "$HOST",
  "apps_domain": "$APPS_DOMAIN",
  "email": "$EMAIL",
  "kit": "master-harness vps-kit",
  "set_up": "$(date +%Y-%m-%d)"
}
EOF

say "Testing: ssh vps version"
if ssh -o BatchMode=yes vps version; then
  echo
  echo "All set. Claude can now run 'ssh vps <command>' and 'git push vps main' from any project."
  echo "It can only do what vps-agent allows (create, deploy, status, logs, env, backups, tls, rollback)."
  [[ -n "$APPS_DOMAIN" ]] && echo "One DNS step left (once, ever): an A record for *.$APPS_DOMAIN pointing to $HOST."
  [[ -z "$APPS_DOMAIN" ]] && echo "Tip: re-run with an apps domain (e.g. apps.example.com) + one wildcard DNS record, and new apps need no DNS work at all."
else
  echo "The test failed. Check that you can log in as $ADMIN, then re-run this script." >&2
  exit 1
fi
