#!/usr/bin/env bash
# Link Workbench into Claude Code and Codex. Symlinks only, so edits here are live.
# Usage: ./install.sh [link|unlink|status] [--dry-run]
# Discovers artifacts by convention, so adding a skill, agent or script needs no edit here.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ACTION="${1:-status}"
DRY="${2:-}"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
BIN_DIR="${WB_BIN_DIR:-$HOME/.local/bin}"

# Emit "source<TAB>target" for everything Workbench manages.
links() {
  printf '%s\t%s\n' "$ROOT/instructions.md" "$CLAUDE_HOME/CLAUDE.md"
  [[ -d "$CODEX_HOME" ]] && printf '%s\t%s\n' "$ROOT/instructions.md" "$CODEX_HOME/AGENTS.md"
  for d in "$ROOT"/skills/*/; do
    [[ -f "$d/SKILL.md" ]] || continue
    name="$(basename "$d")"
    printf '%s\t%s\n' "${d%/}" "$CLAUDE_HOME/skills/$name"
    [[ -d "$CODEX_HOME" ]] && printf '%s\t%s\n' "${d%/}" "$CODEX_HOME/skills/$name"
  done
  for f in "$ROOT"/agents/*.md; do
    [[ -f "$f" ]] && printf '%s\t%s\n' "$f" "$CLAUDE_HOME/agents/$(basename "$f")"
  done
  for f in "$ROOT"/bin/*; do
    [[ -f "$f" ]] && printf '%s\t%s\n' "$f" "$BIN_DIR/$(basename "$f")"
  done
  return 0
}

run() { if [[ "$DRY" == "--dry-run" ]]; then echo "would: $*"; else "$@"; fi; }

while IFS=$'\t' read -r src dst; do
  current="$(readlink "$dst" 2>/dev/null || true)"
  case "$ACTION" in
    status)
      if [[ "$current" == "$src" ]]; then echo "linked    $dst"
      elif [[ -e "$dst" || -L "$dst" ]]; then echo "CONFLICT  $dst (exists, not managed by Workbench)"
      else echo "missing   $dst"; fi ;;
    link)
      if [[ "$current" == "$src" ]]; then continue
      elif [[ -e "$dst" || -L "$dst" ]]; then echo "skip      $dst (exists; move it aside to let Workbench manage it)"
      else run mkdir -p "$(dirname "$dst")"; run ln -s "$src" "$dst"; echo "linked    $dst"; fi ;;
    unlink)
      if [[ "$current" == "$src" ]]; then run rm "$dst"; echo "removed   $dst"; fi ;;
    *) echo "usage: $0 [link|unlink|status] [--dry-run]" >&2; exit 2 ;;
  esac
done < <(links)

if [[ "$ACTION" == "link" && ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "note: $BIN_DIR is not on PATH; add it so 'wb' and 'diff-summary' resolve."
fi
