"""Generate references/subjects/*.json.

Run from the repo root:  python tools/generate_subjects.py
Every numeric value is written as {"value": ..., "_note": "..."}.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "references" / "subjects"
OUT.mkdir(parents=True, exist_ok=True)


def n(value, note):
    return {"value": value, "_note": note}


def t(tid, name, minutes, grading, keywords, note=None):
    return {
        "id": tid,
        "name": name,
        "minutes": n(minutes, note or "按该科常见单题用时估计；来自教学经验初值，可调"),
        "grading": grading,
        "keywords": keywords,
    }


def profile(
    subject, label, prefix, match, keywords, negative, types,
    daily, phase, mastery, difficulty, intervals, thresholds, rates,
    safety, checkers, kind_minutes, mock, proof, per_kp,
):
    return {
        "subject": subject,
        "label": label,
        "biliPrefix": prefix,
        "matchKeywords": match,
        "keywords": keywords,
        "negative": negative,
        "questionTypes": types,
        "typeFallback": {
            "选择题": types[0]["id"],
            "填空题": types[1]["id"] if len(types) > 1 else types[0]["id"],
            "判断题": types[0]["id"],
            "简答题": next((x["id"] for x in types if "简答" in x["name"]), types[-1]["id"]),
            "计算题": next((x["id"] for x in types if "计算" in x["name"]), types[-1]["id"]),
            "证明题": next((x["id"] for x in types if "证明" in x["name"]), types[-1]["id"]),
            "案例题": next((x["id"] for x in types if "案例" in x["name"]), types[-1]["id"]),
            "论述题": next((x["id"] for x in types if "论述" in x["name"]), types[-1]["id"]),
            "综合题": next((x["id"] for x in types if "综合" in x["name"]), types[-1]["id"]),
        },
        "dailyMix": {k: n(v, f"{label}的日常配比初值；按题型覆盖与遗忘规律估计，可调") for k, v in daily.items()},
        "phaseRatio": {k: n(v, f"{label}的阶段比例；计算型偏构建/强化，背诵型偏冲刺，经验初值") for k, v in phase.items()},
        "masteryWeights": {k: n(v, f"{label}的掌握维度权重；依据学科认知任务估计，可调") for k, v in mastery.items()},
        "difficultyWeights": {k: n(v, f"{label}的 D 权重初值；依据该科失分来源估计，可调") for k, v in difficulty.items()},
        "reviewIntervals": [{"days": n(x, "间隔效应初值；背诵型更密，计算型更疏，可调")} for x in intervals],
        "masteryThresholds": {k: n(v, f"{label}的 {k} 正确率阈值；经验初值，可调") for k, v in thresholds.items()},
        "masteryScoreRates": {k: n(v, f"{label}的 {k} 预估得分率；用于目标分量化，经验初值") for k, v in rates.items()},
        "safetyFactor": n(safety, f"{label}的目标分安全系数；题风/难度波动越大越高，经验初值"),
        "checkers": checkers,
        "kindMinutes": {k: n(v, f"{label}的 {k} 题平均用时；经验初值") for k, v in kind_minutes.items()},
        "mockQuestions": n(mock, f"{label}最后一天模拟题量；按考试时长/题型结构估计，可调"),
        "proofQuestions": n(proof, f"{label}最后一天附加证明/拔高题量；经验初值"),
        "minutesPerKp": n(per_kp, f"{label}单个知识点的首学用时；按章节粒度估计，可调"),
    }


COMMON_NEG = ["中职英语", "考研英语", "四级", "六级", "雅思", "托福", "直播", "带货", "vlog", "美食", "舞蹈", "游戏", "开箱", "手机测评"]

profiles = {}

profiles["cs_systems"] = profile(
    "cs_systems", "计算机系统/组成/OS", "计算机系统",
    ["补码", "IEEE754", "汇编", "寄存器", "栈帧", "虚拟内存", "页表", "进程", "系统调用", "x86", "ModRM", "ELF", "操作系统", "计算机组成", "体系结构"],
    ["补码", "原码", "移码", "浮点", "IEEE754", "汇编", "寄存器", "机器码", "指令", "栈帧", "链接", "重定位", "虚拟内存", "页表", "缓存", "局部性", "异常", "中断", "进程", "系统调用", "x86", "ModRM", "ELF", "操作系统", "计算机组成", "体系结构"],
    COMMON_NEG + ["ESP32", "单片机", "嵌入式", "前端", "Java", "Python", "机器学习", "深度学习", "数据分析", "游戏开发", "装机", "电脑维修"],
    [
        t("T1", "数制与编码转换", 8, "auto_exact", ["进制", "十六进制", "二进制", "转换"]),
        t("T2", "整数表示与运算", 10, "auto_exact", ["补码", "原码", "移码", "溢出", "标志位"]),
        t("T3", "浮点表示", 10, "auto_exact", ["浮点", "IEEE754", "阶码", "尾数"]),
        t("T4", "浮点运算与舍入", 12, "auto_numeric", ["舍入", "浮点运算", "精度"]),
        t("T5", "数据对齐与布局", 10, "auto_exact", ["对齐", "填充", "字节序", "大小端"]),
        t("T6", "汇编阅读与寻址", 15, "auto_exact", ["汇编", "寻址", "寄存器", "机器码", "ModRM"]),
        t("T7", "条件跳转与循环", 12, "rubric", ["循环", "跳转", "条件码"]),
        t("T8", "过程调用与栈帧", 15, "rubric", ["栈帧", "调用", "返回地址", "esp", "ebp"]),
        t("T9", "数组与指针", 12, "rubric", ["数组", "指针", "二维"]),
        t("T10", "结构体/联合体", 10, "auto_exact", ["结构体", "联合体", "枚举"]),
        t("T11", "链接与符号", 12, "rubric", ["链接", "符号", "静态库", "动态库"]),
        t("T12", "重定位与 ELF", 12, "auto_exact", ["重定位", "ELF", "目标文件"]),
        t("T13", "异常与中断", 10, "rubric", ["异常", "中断", "信号", "陷阱"]),
        t("T14", "进程与系统调用", 12, "rubric", ["进程", "fork", "exec", "系统调用"]),
        t("T15", "存储层次与缓存", 12, "auto_numeric", ["缓存", "局部性", "命中率"]),
        t("T16", "程序优化与性能", 15, "rubric", ["优化", "性能", "CPI", "流水线"]),
    ],
    {"basic": 0.35, "past": 0.30, "advanced": 0.35, "recite": 0.0},
    {"build": 0.40, "reinforce": 0.35, "sprint": 0.25},
    {"understand": 0.35, "memory": 0.15, "calculation": 0.30, "application": 0.20},
    {"pastLoss": 0.35, "userError": 0.30, "prereqDepth": 0.20, "errorFlags": 0.15},
    [1, 3, 7, 14], {"L1": 0.0, "L2": 0.70, "L3": 0.80, "L4": 0.85},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.10, ["twos", "ieee754", "ieee754_decode", "flags", "modrm", "machine", "choice"],
    {"basic": 10, "past": 14, "advanced": 18, "recite": 0, "mock": 12, "proof": 15},
    10, 2, 12,
)

profiles["programming"] = profile(
    "programming", "程序设计（C/C++/Java/Python）", "编程",
    ["C++", "Java", "Python", "指针", "继承", "多态", "模板", "异常", "递归", "类", "对象", "STL", "装饰器"],
    ["C++", "Java", "Python", "类", "对象", "继承", "多态", "虚函数", "模板", "STL", "指针", "引用", "递归", "异常", "装饰器", "生成器", "并发"],
    COMMON_NEG + ["考研数学", "数据结构考研", "算法竞赛", "前端", "JavaScript", "Go 语言", "Rust", "C#"],
    [
        t("T1", "语法与语义", 6, "auto_exact", ["语法", "类型", "运算符", "作用域"]),
        t("T2", "阅读程序", 10, "auto_exact", ["输出", "程序阅读", "打印"]),
        t("T3", "指针与内存", 12, "rubric", ["指针", "引用", "内存", "new", "delete"]),
        t("T4", "递归与分治", 12, "rubric", ["递归", "分治", "回溯"]),
        t("T5", "面向对象", 12, "rubric", ["类", "继承", "多态", "虚函数", "封装"]),
        t("T6", "异常与资源", 10, "rubric", ["异常", "RAII", "资源", "析构"]),
        t("T7", "STL/容器", 10, "rubric", ["STL", "vector", "map", "迭代器"]),
        t("T8", "设计题", 15, "rubric", ["设计", "接口", "模式"]),
        t("T9", "调试与测试", 10, "rubric", ["调试", "测试", "边界"]),
        t("T10", "综合项目", 18, "rubric", ["综合", "项目", "实现"]),
    ],
    {"basic": 0.35, "past": 0.28, "advanced": 0.37, "recite": 0.0},
    {"build": 0.42, "reinforce": 0.33, "sprint": 0.25},
    {"understand": 0.30, "memory": 0.10, "calculation": 0.30, "application": 0.30},
    {"pastLoss": 0.30, "userError": 0.35, "prereqDepth": 0.15, "errorFlags": 0.20},
    [1, 3, 7, 14], {"L1": 0.0, "L2": 0.70, "L3": 0.80, "L4": 0.85},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.08, ["choice", "exact", "numeric"],
    {"basic": 8, "past": 12, "advanced": 16, "recite": 0, "mock": 10, "proof": 12},
    8, 1, 10,
)

profiles["data_structures"] = profile(
    "data_structures", "数据结构与算法", "数据结构",
    ["时间复杂度", "空间复杂度", "二叉树", "图", "排序", "查找", "哈希", "动态规划", "栈", "队列", "链表", "堆"],
    ["时间复杂度", "空间复杂度", "二叉树", "平衡树", "图", "最短路", "排序", "查找", "哈希", "动态规划", "贪心", "栈", "队列", "链表", "堆"],
    COMMON_NEG + ["考研数学", "数据库", "前端", "Java", "Python", "机器学习"],
    [
        t("T1", "复杂度分析", 6, "auto_numeric", ["复杂度", "O(", "时间", "空间"]),
        t("T2", "线性表", 8, "auto_exact", ["链表", "顺序表", "栈", "队列"]),
        t("T3", "树与二叉树", 12, "rubric", ["二叉树", "遍历", "平衡树", "堆"]),
        t("T4", "图", 14, "rubric", ["图", "最短路", "生成树", "拓扑"]),
        t("T5", "排序", 10, "auto_numeric", ["排序", "快排", "归并", "堆排序"]),
        t("T6", "查找", 8, "auto_numeric", ["查找", "二分", "哈希"]),
        t("T7", "哈希", 8, "rubric", ["哈希", "冲突", "装载因子"]),
        t("T8", "动态规划", 15, "rubric", ["动态规划", "状态转移", "背包"]),
        t("T9", "贪心与回溯", 12, "rubric", ["贪心", "回溯", "剪枝"]),
        t("T10", "综合设计", 18, "rubric", ["综合", "设计", "实现"]),
    ],
    {"basic": 0.30, "past": 0.30, "advanced": 0.40, "recite": 0.0},
    {"build": 0.40, "reinforce": 0.36, "sprint": 0.24},
    {"understand": 0.30, "memory": 0.10, "calculation": 0.35, "application": 0.25},
    {"pastLoss": 0.30, "userError": 0.30, "prereqDepth": 0.20, "errorFlags": 0.20},
    [1, 3, 7, 14], {"L1": 0.0, "L2": 0.70, "L3": 0.80, "L4": 0.85},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.08, ["choice", "numeric", "exact"],
    {"basic": 8, "past": 12, "advanced": 18, "recite": 0, "mock": 10, "proof": 15},
    8, 1, 10,
)

profiles["math"] = profile(
    "math", "高等数学/线性代数/概率统计", "数学",
    ["极限", "导数", "积分", "级数", "微分方程", "矩阵", "行列式", "特征值", "概率", "分布", "期望", "方差", "函数", "连续"],
    ["极限", "导数", "积分", "级数", "微分方程", "矩阵", "行列式", "特征值", "特征向量", "概率", "分布", "期望", "方差", "函数", "连续", "收敛"],
    COMMON_NEG + ["考研政治", "考研英语", "计算机", "编程", "机器学习"],
    [
        t("T1", "选择与填空", 5, "auto_exact", ["选择", "填空", "判断"]),
        t("T2", "公式计算", 10, "auto_numeric", ["计算", "求值", "化简"]),
        t("T3", "极限", 10, "auto_numeric", ["极限", "洛必达", "等价无穷小"]),
        t("T4", "导数与微分", 10, "auto_numeric", ["导数", "微分", "切线"]),
        t("T5", "积分", 12, "auto_numeric", ["积分", "原函数", "换元"]),
        t("T6", "级数", 12, "auto_numeric", ["级数", "收敛", "幂级数"]),
        t("T7", "微分方程", 12, "auto_numeric", ["微分方程", "通解", "特解"]),
        t("T8", "矩阵与行列式", 12, "auto_numeric", ["矩阵", "行列式", "秩", "逆"]),
        t("T9", "特征值与特征向量", 12, "auto_numeric", ["特征值", "特征向量", "对角化"]),
        t("T10", "概率统计", 12, "auto_numeric", ["概率", "分布", "期望", "方差"]),
        t("T11", "证明题", 15, "rubric", ["证明", "求证", "推导"]),
        t("T12", "综合应用", 18, "rubric", ["综合", "应用", "建模"]),
    ],
    {"basic": 0.28, "past": 0.34, "advanced": 0.38, "recite": 0.0},
    {"build": 0.45, "reinforce": 0.35, "sprint": 0.20},
    {"understand": 0.25, "memory": 0.10, "calculation": 0.40, "application": 0.25},
    {"pastLoss": 0.40, "userError": 0.25, "prereqDepth": 0.20, "errorFlags": 0.15},
    [1, 2, 5, 10, 21], {"L1": 0.0, "L2": 0.70, "L3": 0.80, "L4": 0.85},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.08, ["numeric", "matrix", "determinant", "exact", "choice"],
    {"basic": 8, "past": 12, "advanced": 18, "recite": 0, "mock": 14, "proof": 15},
    6, 2, 12,
)

profiles["physics"] = profile(
    "physics", "大学物理", "大学物理",
    ["力学", "电磁", "热学", "光学", "量子", "波动", "电场", "磁场", "动量", "能量"],
    ["力学", "电磁", "热学", "光学", "量子", "波动", "电场", "磁场", "动量", "能量", "刚体", "熵"],
    COMMON_NEG + ["考研政治", "考研英语", "计算机", "编程"],
    [
        t("T1", "选择与填空", 5, "auto_exact", ["选择", "填空"]),
        t("T2", "公式计算", 10, "auto_numeric", ["计算", "求值"]),
        t("T3", "力学", 12, "auto_numeric", ["力学", "受力", "动量", "能量"]),
        t("T4", "电磁学", 12, "auto_numeric", ["电场", "磁场", "电磁"]),
        t("T5", "热学", 10, "auto_numeric", ["热学", "熵", "热力学"]),
        t("T6", "光学", 10, "auto_numeric", ["光学", "干涉", "衍射"]),
        t("T7", "近代物理", 10, "auto_numeric", ["量子", "光电", "相对论"]),
        t("T8", "证明与推导", 15, "rubric", ["证明", "推导"]),
        t("T9", "实验题", 12, "rubric", ["实验", "误差", "数据处理"]),
        t("T10", "综合应用", 18, "rubric", ["综合", "应用"]),
    ],
    {"basic": 0.30, "past": 0.34, "advanced": 0.36, "recite": 0.0},
    {"build": 0.38, "reinforce": 0.37, "sprint": 0.25},
    {"understand": 0.25, "memory": 0.15, "calculation": 0.35, "application": 0.25},
    {"pastLoss": 0.35, "userError": 0.25, "prereqDepth": 0.25, "errorFlags": 0.15},
    [1, 2, 5, 10, 21], {"L1": 0.0, "L2": 0.70, "L3": 0.80, "L4": 0.85},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.10, ["numeric", "choice", "exact"],
    {"basic": 8, "past": 12, "advanced": 18, "recite": 0, "mock": 14, "proof": 12},
    7, 1, 10,
)

profiles["circuits"] = profile(
    "circuits", "电路/模电/数电", "电路",
    ["电路", "节点", "回路", "运放", "三极管", "逻辑门", "触发器", "时序", "放大", "滤波"],
    ["电路", "节点", "回路", "运放", "三极管", "逻辑门", "触发器", "时序", "放大", "滤波", "功放", "数电", "模电"],
    COMMON_NEG + ["考研政治", "考研英语", "计算机", "编程"],
    [
        t("T1", "选择与填空", 5, "auto_exact", ["选择", "填空"]),
        t("T2", "直流电路计算", 12, "auto_numeric", ["电路", "节点", "回路", "电阻"]),
        t("T3", "交流电路计算", 12, "auto_numeric", ["交流", "相量", "阻抗"]),
        t("T4", "模电分析", 14, "auto_numeric", ["三极管", "运放", "放大"]),
        t("T5", "数电分析", 12, "auto_numeric", ["逻辑门", "触发器", "时序"]),
        t("T6", "波形与真值表", 8, "auto_exact", ["波形", "真值表", "卡诺图"]),
        t("T7", "证明与推导", 15, "rubric", ["证明", "推导"]),
        t("T8", "实验题", 12, "rubric", ["实验", "测量", "误差"]),
        t("T9", "综合设计", 18, "rubric", ["设计", "综合"]),
        t("T10", "综合分析", 15, "rubric", ["分析", "综合"]),
    ],
    {"basic": 0.28, "past": 0.36, "advanced": 0.36, "recite": 0.0},
    {"build": 0.40, "reinforce": 0.34, "sprint": 0.26},
    {"understand": 0.25, "memory": 0.15, "calculation": 0.35, "application": 0.25},
    {"pastLoss": 0.35, "userError": 0.25, "prereqDepth": 0.25, "errorFlags": 0.15},
    [1, 2, 5, 10, 21], {"L1": 0.0, "L2": 0.70, "L3": 0.80, "L4": 0.85},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.10, ["numeric", "choice", "exact"],
    {"basic": 8, "past": 12, "advanced": 18, "recite": 0, "mock": 14, "proof": 12},
    7, 1, 10,
)

profiles["chemistry_biology"] = profile(
    "chemistry_biology", "化学/生物类", "化学",
    ["化学", "反应", "方程式", "有机", "无机", "分析", "细胞", "蛋白", "代谢", "遗传"],
    ["化学", "反应", "方程式", "有机", "无机", "分析", "细胞", "蛋白", "代谢", "遗传", "酶", "分子"],
    COMMON_NEG + ["考研政治", "考研英语", "计算机", "编程"],
    [
        t("T1", "选择与填空", 5, "auto_exact", ["选择", "填空"]),
        t("T2", "化学计算", 10, "auto_numeric", ["计算", "摩尔", "浓度"]),
        t("T3", "方程式与机理", 12, "rubric", ["方程式", "反应", "机理"]),
        t("T4", "有机结构", 12, "rubric", ["有机", "结构", "官能团"]),
        t("T5", "无机/分析", 10, "auto_numeric", ["无机", "分析", "滴定"]),
        t("T6", "细胞与代谢", 12, "recite", ["细胞", "代谢", "酶"]),
        t("T7", "遗传与分子", 12, "recite", ["遗传", "DNA", "蛋白"]),
        t("T8", "简答与名词", 8, "recite", ["简答", "名词", "概念"]),
        t("T9", "实验题", 12, "rubric", ["实验", "步骤", "误差"]),
        t("T10", "综合应用", 15, "rubric", ["综合", "应用"]),
    ],
    {"basic": 0.30, "past": 0.30, "advanced": 0.25, "recite": 0.15},
    {"build": 0.35, "reinforce": 0.35, "sprint": 0.30},
    {"understand": 0.30, "memory": 0.30, "calculation": 0.20, "application": 0.20},
    {"pastLoss": 0.30, "userError": 0.30, "prereqDepth": 0.20, "errorFlags": 0.20},
    [1, 2, 4, 7, 14], {"L1": 0.0, "L2": 0.70, "L3": 0.80, "L4": 0.85},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.12, ["exact", "numeric", "choice"],
    {"basic": 8, "past": 12, "advanced": 16, "recite": 6, "mock": 12, "proof": 10},
    8, 1, 10,
)

profiles["medicine"] = profile(
    "medicine", "医学基础", "医学",
    ["解剖", "生理", "病理", "药理", "诊断", "治疗", "症状", "免疫", "感染", "临床"],
    ["解剖", "生理", "病理", "药理", "诊断", "治疗", "症状", "免疫", "感染", "临床", "病例"],
    COMMON_NEG + ["考研政治", "考研英语", "计算机", "编程"],
    [
        t("T1", "单选题", 3, "auto_exact", ["选择", "单选"]),
        t("T2", "多选题", 4, "auto_exact", ["多选"]),
        t("T3", "判断题", 3, "auto_exact", ["判断"]),
        t("T4", "名词解释", 5, "recite", ["名词", "解释"]),
        t("T5", "简答题", 8, "recite", ["简答"]),
        t("T6", "病例分析", 15, "rubric", ["病例", "分析", "诊断"]),
        t("T7", "诊断与治疗", 12, "rubric", ["诊断", "治疗", "方案"]),
        t("T8", "综合论述", 15, "rubric", ["论述", "综合"]),
        t("T9", "实验/技能", 10, "rubric", ["实验", "技能", "操作"]),
    ],
    {"basic": 0.25, "past": 0.30, "advanced": 0.20, "recite": 0.25},
    {"build": 0.36, "reinforce": 0.34, "sprint": 0.30},
    {"understand": 0.25, "memory": 0.40, "calculation": 0.15, "application": 0.20},
    {"pastLoss": 0.25, "userError": 0.40, "prereqDepth": 0.15, "errorFlags": 0.20},
    [1, 2, 4, 7, 10, 14], {"L1": 0.0, "L2": 0.72, "L3": 0.82, "L4": 0.87},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.12, ["choice", "exact"],
    {"basic": 6, "past": 10, "advanced": 14, "recite": 6, "mock": 10, "proof": 8},
    8, 0, 10,
)

profiles["law"] = profile(
    "law", "法学", "法学",
    ["法条", "构成要件", "违约责任", "侵权", "合同", "刑法", "民法", "诉讼", "管辖", "证据", "判决"],
    ["法条", "构成要件", "违约责任", "侵权", "合同", "刑法", "民法", "诉讼", "管辖", "证据", "判决", "要约", "承诺"],
    COMMON_NEG + ["考研数学", "考研英语", "计算机", "编程"],
    [
        t("T1", "单选题", 3, "auto_exact", ["选择", "单选"]),
        t("T2", "多选题", 4, "auto_exact", ["多选"]),
        t("T3", "判断题", 3, "auto_exact", ["判断"]),
        t("T4", "名词解释", 5, "recite", ["名词", "解释"]),
        t("T5", "简答题", 8, "recite", ["简答"]),
        t("T6", "论述题", 15, "rubric", ["论述", "评价"]),
        t("T7", "法条分析", 10, "rubric", ["法条", "解释", "适用"]),
        t("T8", "案例分析", 15, "rubric", ["案例", "分析", "判决"]),
        t("T9", "综合题", 18, "rubric", ["综合", "程序"]),
    ],
    {"basic": 0.15, "past": 0.35, "advanced": 0.20, "recite": 0.30},
    {"build": 0.30, "reinforce": 0.35, "sprint": 0.35},
    {"understand": 0.25, "memory": 0.40, "calculation": 0.10, "application": 0.25},
    {"pastLoss": 0.20, "userError": 0.45, "prereqDepth": 0.15, "errorFlags": 0.20},
    [1, 2, 3, 5, 7, 10, 14], {"L1": 0.0, "L2": 0.72, "L3": 0.82, "L4": 0.88},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.12, ["choice", "exact"],
    {"basic": 6, "past": 10, "advanced": 14, "recite": 6, "mock": 10, "proof": 8},
    8, 0, 10,
)

profiles["economics"] = profile(
    "economics", "经济/金融/会计", "经济学",
    ["供给", "需求", "弹性", "边际", "效用", "均衡", "GDP", "通货膨胀", "货币政策", "财政政策", "博弈", "会计"],
    ["供给", "需求", "弹性", "边际", "效用", "均衡", "GDP", "通货膨胀", "货币政策", "财政政策", "博弈", "会计", "资产", "负债"],
    COMMON_NEG + ["考研数学", "考研英语", "计算机", "编程"],
    [
        t("T1", "单选题", 3, "auto_exact", ["选择", "单选"]),
        t("T2", "计算题", 12, "auto_numeric", ["计算", "弹性", "GDP"]),
        t("T3", "名词解释", 5, "recite", ["名词", "解释"]),
        t("T4", "简答题", 8, "recite", ["简答"]),
        t("T5", "论述题", 15, "rubric", ["论述", "评价"]),
        t("T6", "图表分析", 10, "rubric", ["图表", "曲线", "分析"]),
        t("T7", "模型推导", 12, "rubric", ["模型", "推导", "均衡"]),
        t("T8", "案例分析", 15, "rubric", ["案例", "分析"]),
        t("T9", "综合题", 18, "rubric", ["综合", "政策"]),
    ],
    {"basic": 0.25, "past": 0.30, "advanced": 0.30, "recite": 0.15},
    {"build": 0.35, "reinforce": 0.36, "sprint": 0.29},
    {"understand": 0.30, "memory": 0.25, "calculation": 0.25, "application": 0.20},
    {"pastLoss": 0.30, "userError": 0.30, "prereqDepth": 0.20, "errorFlags": 0.20},
    [1, 2, 4, 7, 10, 14], {"L1": 0.0, "L2": 0.70, "L3": 0.80, "L4": 0.85},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.10, ["numeric", "exact", "choice"],
    {"basic": 8, "past": 12, "advanced": 16, "recite": 6, "mock": 10, "proof": 10},
    8, 1, 10,
)

profiles["politics"] = profile(
    "politics", "政治/马原/思修类", "政治",
    ["马原", "毛中特", "思修", "史纲", "唯物", "辩证法", "商品", "剩余价值", "社会主义", "价值观"],
    ["马原", "毛中特", "思修", "史纲", "唯物", "辩证法", "商品", "剩余价值", "社会主义", "价值观", "人生观", "法治"],
    COMMON_NEG + ["考研数学", "考研英语", "计算机", "编程"],
    [
        t("T1", "单选题", 2, "auto_exact", ["选择", "单选"]),
        t("T2", "多选题", 3, "auto_exact", ["多选"]),
        t("T3", "判断题", 2, "auto_exact", ["判断"]),
        t("T4", "简答题", 8, "recite", ["简答"]),
        t("T5", "材料分析", 12, "rubric", ["材料", "分析"]),
        t("T6", "论述题", 15, "rubric", ["论述"]),
        t("T7", "背诵默写", 6, "recite", ["背诵", "默写", "原理"]),
        t("T8", "综合题", 15, "rubric", ["综合"]),
    ],
    {"basic": 0.15, "past": 0.25, "advanced": 0.20, "recite": 0.40},
    {"build": 0.25, "reinforce": 0.30, "sprint": 0.45},
    {"understand": 0.20, "memory": 0.50, "calculation": 0.05, "application": 0.25},
    {"pastLoss": 0.15, "userError": 0.50, "prereqDepth": 0.10, "errorFlags": 0.25},
    [1, 2, 3, 5, 7, 10, 14], {"L1": 0.0, "L2": 0.75, "L3": 0.85, "L4": 0.90},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.15, ["choice", "exact"],
    {"basic": 5, "past": 8, "advanced": 12, "recite": 5, "mock": 8, "proof": 6},
    8, 0, 10,
)

profiles["foreign_language"] = profile(
    "foreign_language", "外语类", "英语",
    ["词汇", "语法", "阅读", "完形", "翻译", "写作", "听力", "口语", "长难句"],
    ["词汇", "语法", "阅读", "完形", "翻译", "写作", "听力", "口语", "长难句", "作文"],
    ["考研政治", "考研数学", "计算机", "编程", "直播", "带货", "美食", "舞蹈"],
    [
        t("T1", "词汇与语法", 3, "auto_exact", ["词汇", "语法", "选择"]),
        t("T2", "阅读理解", 12, "rubric", ["阅读", "理解"]),
        t("T3", "完形填空", 10, "auto_exact", ["完形", "填空"]),
        t("T4", "翻译", 12, "rubric", ["翻译", "英译汉", "汉译英"]),
        t("T5", "写作", 20, "rubric", ["写作", "作文"]),
        t("T6", "听力", 12, "rubric", ["听力"]),
        t("T7", "口语", 12, "rubric", ["口语", "朗读"]),
        t("T8", "长难句", 8, "rubric", ["长难句", "句法"]),
        t("T9", "综合", 18, "rubric", ["综合"]),
    ],
    {"basic": 0.20, "past": 0.30, "advanced": 0.20, "recite": 0.30},
    {"build": 0.30, "reinforce": 0.30, "sprint": 0.40},
    {"understand": 0.20, "memory": 0.45, "calculation": 0.10, "application": 0.25},
    {"pastLoss": 0.20, "userError": 0.45, "prereqDepth": 0.15, "errorFlags": 0.20},
    [1, 2, 3, 5, 7, 10, 14], {"L1": 0.0, "L2": 0.72, "L3": 0.82, "L4": 0.88},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.12, ["choice", "exact"],
    {"basic": 5, "past": 8, "advanced": 14, "recite": 5, "mock": 8, "proof": 6},
    8, 0, 10,
)

profiles["general"] = profile(
    "general", "通用兜底", "",
    ["课程", "考试", "复习", "重点", "知识点"],
    ["课程", "考试", "复习", "重点", "知识点", "概念", "原理", "方法", "应用"],
    COMMON_NEG,
    [
        t("T1", "概念辨析", 5, "auto_exact", ["概念", "辨析", "选择"]),
        t("T2", "性质判断", 5, "auto_exact", ["判断", "性质"]),
        t("T3", "公式计算", 10, "auto_numeric", ["计算", "公式"]),
        t("T4", "推导证明", 12, "rubric", ["证明", "推导"]),
        t("T5", "图表分析", 10, "rubric", ["图表", "分析"]),
        t("T6", "案例分析", 15, "rubric", ["案例", "分析"]),
        t("T7", "流程设计", 12, "rubric", ["流程", "设计"]),
        t("T8", "比较异同", 8, "rubric", ["比较", "异同"]),
        t("T9", "综合应用", 15, "rubric", ["综合", "应用"]),
        t("T10", "实验/实践", 12, "rubric", ["实验", "实践"]),
    ],
    {"basic": 0.30, "past": 0.30, "advanced": 0.30, "recite": 0.10},
    {"build": 0.35, "reinforce": 0.35, "sprint": 0.30},
    {"understand": 0.25, "memory": 0.25, "calculation": 0.25, "application": 0.25},
    {"pastLoss": 0.30, "userError": 0.30, "prereqDepth": 0.20, "errorFlags": 0.20},
    [1, 3, 7, 14], {"L1": 0.0, "L2": 0.70, "L3": 0.80, "L4": 0.85},
    {"L0": 0.0, "L1": 0.30, "L2": 0.70, "L3": 0.85, "L4": 0.95},
    1.10, ["choice", "exact", "numeric"],
    {"basic": 8, "past": 12, "advanced": 16, "recite": 6, "mock": 10, "proof": 10},
    8, 1, 10,
)

if __name__ == "__main__":
    for name, data in profiles.items():
        if name != data["subject"]:
            raise SystemExit(f"subject mismatch: {name} vs {data['subject']}")
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote", path)
