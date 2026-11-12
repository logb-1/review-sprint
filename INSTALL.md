# 安装 review-sprint

这是一个“便携 skill 包 + 一键安装脚本”，不是 `.exe` / `.msi` 系统安装器。

## Windows（双击）

1. 解压 `review-sprint-skill-0.4.7.zip`，进入解压后的 `review-sprint` 目录。
2. 双击 `install.cmd`。
3. 安装器会：
   - 检查 Python 3.10+；
   - 自动探测本机已有的 DSH / Claude Code / Codex / Cursor 目录；
   - 询问是否安装可选依赖；
   - 安装 skill，最后打印 `coach.py --version` 验证结果。

命令行方式：

```powershell
.\install.cmd
.\install.cmd --target all --yes
.\install.cmd --target custom --destination "D:\skills\review-sprint"
.\install.cmd --no-deps
```

## macOS / Linux / Git Bash

```bash
chmod +x install.sh
./install.sh
./install.sh --target all --yes
./install.sh --target custom --destination /tmp/review-sprint
```

## 参数

| 参数 | 作用 |
|---|---|
| `--target auto` | 默认；自动探测已有 agent 目录 |
| `--target dsh` | 只装 DSH |
| `--target claude` | 只装 Claude Code |
| `--target codex` | 只装 Codex |
| `--target cursor` | 只装 Cursor |
| `--target all` | 四平台都装 |
| `--target custom` | 需要配合 `--destination` |
| `--yes` | 不询问，适合脚本 |
| `--no-deps` | 跳过可选 Python 依赖 |

## 注意

- 安装器会把 `SKILL.md` 中的 `$SKILL_DIR` 替换为实际安装目录的绝对路径；不要直接使用 zip 内的 `SKILL.md` 原文件。
- DSH 已做端到端验证；Claude Code / Codex / Cursor 目前是安装与格式兼容，加载器和权限行为需在对应客户端再验证。详见 `COMPATIBILITY.md`。
- 可选依赖用于 PDF / DOCX / PPTX 解析；不装也能运行，只是相应输入会降级。
- 安装器不会修改系统 PATH、注册表或系统 Python。
- 需要手动控制时，仍可使用 `scripts/install-skill.ps1` / `scripts/install-skill.sh`。
