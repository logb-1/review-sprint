#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

target="${1:-dsh}"
case "$target" in
  dsh|claude|codex|cursor)
    dest="$HOME/.${target}/skills/review-sprint"
    ;;
  all)
    for name in dsh claude codex cursor; do
      bash "$0" "$name" || exit $?
    done
    exit 0
    ;;
  custom)
    if [[ $# -lt 2 || -z "${2:-}" ]]; then
      echo "custom 安装需要目标目录，例如：bash scripts/install-skill.sh custom /tmp/review-sprint" >&2
      exit 2
    fi
    dest="$2"
    ;;
  *)
    # 兼容旧用法：第一个参数直接是目标目录。
    dest="$target"
    ;;
esac

rm -rf "$dest"
mkdir -p "$dest"
cp "$here/SKILL.md" "$here/SECURITY.md" "$here/COMPATIBILITY.md" \
  "$here/requirements-optional.txt" "$dest/"
cp -R "$here/scripts" "$here/references" "$dest/"
rm -rf "$dest/scripts/__pycache__" "$dest/scripts/review_sprint/__pycache__"

# 写入安装位置绝对路径，避免不同 agent 对 $SKILL_DIR 的约定不一致。
escaped="$(printf '%s' "$dest" | sed 's/[&|]/\\&/g')"
tmp="$dest/SKILL.md.tmp"
sed "s|\\\$SKILL_DIR|$escaped|g" "$dest/SKILL.md" > "$tmp"
mv "$tmp" "$dest/SKILL.md"
chmod +x "$dest/scripts/coach.sh" "$dest/scripts/coach.py" 2>/dev/null || true
echo "Installed review-sprint skill body to $dest"
