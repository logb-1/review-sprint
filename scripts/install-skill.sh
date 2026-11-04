#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dest="${1:-$HOME/.dsh/skills/review-sprint}"
rm -rf "$dest"
mkdir -p "$dest"
cp "$here/SKILL.md" "$dest/"
cp -R "$here/scripts" "$here/references" "$dest/"
find "$dest" -type d -name __pycache__ -prune -exec rm -rf {} +
echo "Installed review-sprint skill body to $dest"
