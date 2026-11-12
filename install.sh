#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
py=""

# A Microsoft Store placeholder is not a usable Python interpreter.
is_store_alias() {
  [[ "$1" == *WindowsApps* ]]
}

if [[ -n "${DSH_PYTHON:-}" && -x "${DSH_PYTHON}" ]]; then
  py="${DSH_PYTHON}"
fi

if [[ -z "$py" ]] && command -v python3 >/dev/null 2>&1; then
  candidate="$(command -v python3)"
  if ! is_store_alias "$candidate"; then py="$candidate"; fi
fi

if [[ -z "$py" ]] && command -v python >/dev/null 2>&1; then
  candidate="$(command -v python)"
  if ! is_store_alias "$candidate"; then py="$candidate"; fi
fi

# Git Bash often has no python3, but DSH ships a bundled interpreter.
if [[ -z "$py" && -d "$HOME/.dsh/dsh-runtimes" ]]; then
  for candidate in "$HOME"/.dsh/dsh-runtimes/*/dependencies/python/python.exe; do
    if [[ -x "$candidate" ]]; then py="$candidate"; break; fi
  done
fi

if [[ -z "$py" ]]; then
  echo "Python 3.10+ was not found. Install Python or set DSH_PYTHON." >&2
  exit 127
fi

exec "$py" -X utf8 "$here/scripts/install.py" "$@"
