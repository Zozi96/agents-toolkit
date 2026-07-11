#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage: ./install-agents.sh [--dry-run]

Installs a global Codex hook, Python helpers, the Codex skill, and legacy
instruction files for other supported agents.

Targets:
  ~/.codex/hooks.json
  ~/.agents/hooks/session-start.{py,ps1}
  ~/.claude/CLAUDE.md
  ~/.pi/agent/AGENTS.md
  ~/.gemini/GEMINI.md
  ~/.agents/scripts/*.py
  ~/.codex/skills/token-efficient-repo-work/

The installer removes only the old agents-toolkit managed block from
~/.codex/AGENTS.md. Other content is preserved.
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

install_hooks_config() {
  local tmp
  tmp="$(mktemp)"
  python3 "${SCRIPTS_SRC}/merge_hooks.py" "${HOOKS_SRC}/hooks.json" "${HOME}/.codex/hooks.json" "$tmp"
  install_file "$tmp" "${HOME}/.codex/hooks.json"
  rm -f "$tmp"
}

remove_codex_agents_block() {
  local dest="${HOME}/.codex/AGENTS.md"
  local tmp
  [ -e "$dest" ] || return 0
  tmp="$(mktemp)"
  python3 "${SCRIPTS_SRC}/merge_md_blocks.py" --remove "$dest" "$tmp"
  if cmp -s "$tmp" "$dest"; then
    rm -f "$tmp"
    return 0
  fi
  if [ ! -s "$tmp" ]; then
    backup_if_changed "$tmp" "$dest" || true
    run rm -f "$dest"
  else
    install_file "$tmp" "$dest"
  fi
  rm -f "$tmp"
  log "Removed agents-toolkit block: $dest"
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
SKILL_SRC="${SCRIPT_DIR}/skills/token-efficient-repo-work"
HOOKS_SRC="${SCRIPT_DIR}/hooks"

[ -f "$AGENTS_SRC" ] || die "Missing ${AGENTS_SRC}"
[ -d "$SCRIPTS_SRC" ] || die "Missing ${SCRIPTS_SRC}"
[ -f "${SKILL_SRC}/SKILL.md" ] || die "Missing ${SKILL_SRC}/SKILL.md"
[ -f "${SKILL_SRC}/agents/openai.yaml" ] || die "Missing ${SKILL_SRC}/agents/openai.yaml"
[ -f "${HOOKS_SRC}/hooks.json" ] || die "Missing ${HOOKS_SRC}/hooks.json"
[ -f "${HOOKS_SRC}/session-start.py" ] || die "Missing ${HOOKS_SRC}/session-start.py"
[ -f "${HOOKS_SRC}/session-start.ps1" ] || die "Missing ${HOOKS_SRC}/session-start.ps1"
find "$SCRIPTS_SRC" -maxdepth 1 -type f -name '*.py' -print -quit | grep -q . || die "No Python helper scripts found in ${SCRIPTS_SRC}"
command -v python3 >/dev/null 2>&1 || die "Python 3 is required"

install_md "$AGENTS_SRC" "${HOME}/.claude/CLAUDE.md"
install_md "$AGENTS_SRC" "${HOME}/.pi/agent/AGENTS.md"
install_md "$AGENTS_SRC" "${HOME}/.gemini/GEMINI.md"

run mkdir -p "${HOME}/.agents/scripts"
for helper in "$SCRIPTS_SRC"/*.py; do
  helper_dest="${HOME}/.agents/scripts/$(basename "$helper")"
  install_file "$helper" "$helper_dest"
  run chmod +x "$helper_dest"
done

install_file "${HOOKS_SRC}/session-start.py" "${HOME}/.agents/hooks/session-start.py"
run chmod +x "${HOME}/.agents/hooks/session-start.py"
install_file "${HOOKS_SRC}/session-start.ps1" "${HOME}/.agents/hooks/session-start.ps1"
install_hooks_config
remove_codex_agents_block

install_file "${SKILL_SRC}/SKILL.md" "${HOME}/.codex/skills/token-efficient-repo-work/SKILL.md"
install_file "${SKILL_SRC}/agents/openai.yaml" "${HOME}/.codex/skills/token-efficient-repo-work/agents/openai.yaml"

log "Done."
log "Codex now uses the global SessionStart hook; ~/.codex/AGENTS.md is no longer managed by this toolkit."
