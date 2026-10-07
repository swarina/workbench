#!/usr/bin/env bash
# Install Workbench into a cloud session VM. Run from the environment's setup script
# once the repo is cloned (see README, "Cloud sessions").
#
# Always exits 0: a broken Workbench must never stop a cloud session from starting.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
export WB_BIN_DIR="${WB_BIN_DIR:-/usr/local/bin}"

step() { "$@" || echo "workbench: '$*' failed, continuing"; }

# The VM ships its own CLAUDE.md, so import ours rather than replace it.
step "$ROOT/install.sh" link --import-instructions
step python3 "$ROOT/bin/wb" wire-hook --settings "$CLAUDE_HOME/settings.json"

# Lets skills tell a cloud VM (state must survive in the PR) from a local machine.
mkdir -p "$CLAUDE_HOME" && : > "$CLAUDE_HOME/.workbench-cloud"
echo "workbench: installed for this cloud session ($ROOT)"
exit 0
