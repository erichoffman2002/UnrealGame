#!/usr/bin/env bash
# Bash wrapper around run_unreal.ps1, for agents that shell out through bash.
# Discovery is NOT reimplemented here; run_unreal.ps1 stays the single source.
#
# Usage:
#   ./run_unreal.sh --script build_test_scene --editor
#   ./run_unreal.sh --script verify_scene
set -euo pipefail

TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PS1_SCRIPT="$TOOLS_DIR/run_unreal.ps1"

SCRIPT_NAME=""
PARAMS=""
EXTRA=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --script|-s)            SCRIPT_NAME="$2"; shift 2 ;;
    --params|-p)            PARAMS="$2"; shift 2 ;;
    --editor)               EXTRA+=("-Editor"); shift ;;
    --project)              EXTRA+=("-Project" "$2"); shift 2 ;;
    --engine-root)          EXTRA+=("-EngineRoot" "$2"); shift 2 ;;
    --allow-editor-running) EXTRA+=("-AllowEditorRunning"); shift ;;
    --timeout)              EXTRA+=("-TimeoutSeconds" "$2"); shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$SCRIPT_NAME" ]]; then echo "error: --script is required" >&2; exit 2; fi

PWSH=""
for candidate in pwsh powershell powershell.exe; do
  if command -v "$candidate" >/dev/null 2>&1; then PWSH="$candidate"; break; fi
done
if [[ -z "$PWSH" ]]; then echo "error: no PowerShell interpreter found" >&2; exit 2; fi

PS1_WIN="$PS1_SCRIPT"
if command -v cygpath >/dev/null 2>&1; then PS1_WIN="$(cygpath -w "$PS1_SCRIPT")"; fi

ARGS=(-NoProfile -ExecutionPolicy Bypass -File "$PS1_WIN" -Script "$SCRIPT_NAME")
if [[ -n "$PARAMS" ]]; then ARGS+=(-Params "$PARAMS"); fi
if [[ ${#EXTRA[@]} -gt 0 ]]; then ARGS+=("${EXTRA[@]}"); fi

exec "$PWSH" "${ARGS[@]}"
