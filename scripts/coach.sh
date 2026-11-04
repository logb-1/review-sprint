#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/coach.py"

if [[ -n "${DSH_PYTHON:-}" ]]; then
  exec "$DSH_PYTHON" "$script" "$@"
fi
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$script" "$@"
fi
if command -v python >/dev/null 2>&1; then
  exec python "$script" "$@"
fi
for candidate in "$HOME"/.dsh/dsh-runtimes/*/dependencies/python/bin/python3; do
  if [[ -x "$candidate" ]]; then
    exec "$candidate" "$script" "$@"
  fi
done
echo "Python 3 not found. Set DSH_PYTHON or install Python 3.10+." >&2
exit 127
