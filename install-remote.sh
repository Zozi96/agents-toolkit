#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
RAW_BASE="${RAW_BASE:-https://raw.githubusercontent.com/Zozi96/agents-toolkit/main}"
FILES=(
  "AGENTS.md"
  "install-agents.sh"
  "scripts/_agent_utils.py"
  "scripts/compact_logs.py"
  "scripts/diff_summary.py"
  "scripts/repo_map.py"
  "scripts/safe_read.py"
  "scripts/scan_errors.py"
  "scripts/summarize_data.py"
  "scripts/summarize_json.py"
  "scripts/summarize_tests.py"
)

usage() {
  cat <<'USAGE'
Usage: install-remote.sh [--raw-base URL] [--dry-run]

Downloads agents-toolkit files to a temporary directory, then installs global
agent instruction files and Python helper scripts.

Examples:
  curl -fsSL https://raw.githubusercontent.com/Zozi96/agents-toolkit/main/install-remote.sh | bash
USAGE
}

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

download() {
  local url="$1"
  local dest="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$dest"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$dest" "$url"
  else
    die "curl or wget is required"
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --raw-base)
      [ "$#" -ge 2 ] || die "--raw-base requires a URL"
      RAW_BASE="${2%/}"
      shift
      ;;
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

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

for file in "${FILES[@]}"; do
  mkdir -p "${TMP_DIR}/$(dirname "$file")"
  download "${RAW_BASE}/${file}" "${TMP_DIR}/${file}"
done

chmod +x "${TMP_DIR}/install-agents.sh"
if [ "$DRY_RUN" -eq 1 ]; then
  "${TMP_DIR}/install-agents.sh" --dry-run
else
  "${TMP_DIR}/install-agents.sh"
fi

log "Downloaded from: ${RAW_BASE}"
