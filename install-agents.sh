#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage: ./install-agents.sh [--dry-run]

Installs global agent instruction files and Python helper scripts.

Targets:
  ~/.codex/AGENTS.md
  ~/.claude/CLAUDE.md
  ~/.pi/agent/AGENTS.md
  ~/.gemini/GEMINI.md
  ~/.agents/scripts/*.py
USAGE
}

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    log "[dry-run] $*"
  else
    "$@"
  fi
}

backup_if_changed() {
  local src="$1"
  local dest="$2"
  local stamp

  if [ ! -e "$dest" ]; then
    return 0
  fi

  if cmp -s "$src" "$dest"; then
    return 1
  fi

  stamp="$(date +%Y%m%d-%H%M%S)"
  run cp "$dest" "${dest}.bak.${stamp}"
  return 0
}

install_file() {
  local src="$1"
  local dest="$2"
  local dest_dir

  dest_dir="$(dirname "$dest")"
  run mkdir -p "$dest_dir"

  if [ -e "$dest" ] && cmp -s "$src" "$dest"; then
    log "Skip unchanged: $dest"
    return 0
  fi

  backup_if_changed "$src" "$dest" || true
  run cp "$src" "$dest"
  log "Installed: $dest"
}

install_md() {
  local src="$1"
  local dest="$2"
  local tmp

  if ! command -v python3 >/dev/null 2>&1; then
    install_file "$src" "$dest"
    return 0
  fi

  # Only the <!-- agents-toolkit --> managed section is replaced; anything
  # other tools wrote to dest (plugin blocks, MCP/skill notes) is kept as-is.
  tmp="$(mktemp)"
  python3 "${SCRIPTS_SRC}/merge_md_blocks.py" "$src" "$dest" "$tmp"
  install_file "$tmp" "$dest"
  rm -f "$tmp"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
  shift
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_SRC="${SCRIPT_DIR}/AGENTS.md"
SCRIPTS_SRC="${SCRIPT_DIR}/scripts"

[ -f "$AGENTS_SRC" ] || die "Missing ${AGENTS_SRC}"
[ -d "$SCRIPTS_SRC" ] || die "Missing ${SCRIPTS_SRC}"
find "$SCRIPTS_SRC" -maxdepth 1 -type f -name '*.py' -print -quit | grep -q . || die "No Python helper scripts found in ${SCRIPTS_SRC}"

install_md "$AGENTS_SRC" "${HOME}/.codex/AGENTS.md"
install_md "$AGENTS_SRC" "${HOME}/.claude/CLAUDE.md"
install_md "$AGENTS_SRC" "${HOME}/.pi/agent/AGENTS.md"
install_md "$AGENTS_SRC" "${HOME}/.gemini/GEMINI.md"

run mkdir -p "${HOME}/.agents/scripts"
for helper in "$SCRIPTS_SRC"/*.py; do
  helper_dest="${HOME}/.agents/scripts/$(basename "$helper")"
  install_file "$helper" "$helper_dest"
  run chmod +x "$helper_dest"
done

log "Done."
log "Antigravity global rules installed at ~/.gemini/GEMINI.md; shared Antigravity skills use a separate path."
