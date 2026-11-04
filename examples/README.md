# 示例：合成 CSAPP 复习材料

这 5 个文件是**合成数据**，用于跑通 `init → plan → today → audit`，不含任何真实试卷或课件。

```bash
python scripts/coach.py --workspace /tmp/demo init \
  --course "计算机系统基础" --exam-date 2026-11-23 \
  --materials examples/demo_csapp --daily-minutes 120
python scripts/coach.py today --workspace /tmp/demo --day 2
```

- `syllabus.md`：考纲与题型分值
- `chapter2.md` / `chapter3.md`：带 `<!-- page: N -->` 页码标记的章节
- `2024-final.md`：24 道合成题
- `2024-final-answers.md`：答案（与试卷自动配对）

真实使用时把 `--materials` 指向你的课件/真题目录即可。
