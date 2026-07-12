"""校领导汇报 PPT —— 朱军案例页六维雷达 + 五轴条形.

读 results/fullevaluation/round2/paper-1322.json 的六维 round2_mean，
读 results/top101-position-assessment-v0.2/merged/paper-1322.json 的五轴 final 分数，
输出六维雷达图与五轴条形图到 docs/presentations/assets/。

口径：六维 final_score 用 report_paper_master.csv 的 weighted_score（E1 加权分 85.2），
与直方图标注一致；round2_final_score_mean(84.42) 不在图上展示，避免双口径混淆。
"""

from __future__ import annotations

import json
from math import pi
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "presentations" / "assets"

SIXDIM_FILE = ROOT / "results" / "fullevaluation" / "round2" / "paper-1322.json"
FIVEAXIS_FILE = ROOT / "results" / "top101-position-assessment-v0.2" / "merged" / "paper-1322.json"
MASTER_CSV = ROOT / "results" / "report_paper_master.csv"

# 六维：旧键 → 中文名（固定顺序，雷达顺时针）
SIXDIM = [
    ("problem_originality", "研究创新性"),
    ("literature_insight", "现状洞察度"),
    ("analytical_framework", "理论建构力"),
    ("logical_coherence", "逻辑连贯性"),
    ("conclusion_consensus", "学术共识度"),
    ("forward_extension", "前瞻延展性"),
]
# 五轴：键 → 中文名
FIVEAXIS = [
    ("object_belonging", "对象归属度"),
    ("material_belonging", "材料归属度"),
    ("category_autonomy", "范畴自主度"),
    ("explanatory_orientation", "解释目标归属度"),
    ("system_mappability", "体系映射度"),
]

ACCENT = "#C8102E"  # 交大红，单系列高亮


def load_sixdim() -> tuple[list[float], float, float]:
    d = json.loads(SIXDIM_FILE.read_text())
    dims = d["dimensions"]
    scores = [float(dims[k]["round2_mean"]) for k, _ in SIXDIM]
    final_mean = float(d["overall"]["round2_final_score_mean"])
    r2_std = float(d["overall"]["round2_avg_std"])
    return scores, final_mean, r2_std


def load_fiveaxis() -> list[int]:
    d = json.loads(FIVEAXIS_FILE.read_text())
    ax = d["final"]["axis_scores"]
    return [int(ax[k]["score"]) for k, _ in FIVEAXIS]


def load_master_weighted(pid: int = 1322) -> float:
    import csv
    with MASTER_CSV.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if int(r["pid"]) == pid:
                return float(r["weighted_score"])
    raise RuntimeError(f"pid {pid} not found in master csv")


def render_sixdim_radar(scores: list[float], weighted: float, r2_std: float) -> None:
    labels = [name for _, name in SIXDIM]
    n = len(labels)
    angles = [i / n * 2 * pi for i in range(n)] + [0]
    vals = scores + [scores[0]]

    plt.rcParams.update({
        "font.sans-serif": ["PingFang SC", "Heiti SC", "Arial Unicode MS", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 150,
    })
    fig, ax = plt.subplots(figsize=(7.5, 6.5), subplot_kw=dict(polar=True))
    ax.set_theta_offset(pi / 2)
    ax.set_theta_direction(-1)

    ax.plot(angles, vals, color=ACCENT, linewidth=2)
    ax.fill(angles, vals, color=ACCENT, alpha=0.18)
    # 各点数值标注
    for ang, v, label in zip(angles[:-1], vals[:-1], labels):
        ax.scatter(ang, v, color=ACCENT, s=28, zorder=5)
        ax.annotate(f"{v:.1f}", xy=(ang, v), xytext=(0, 8),
                    textcoords="offset points", ha="center", fontsize=8.5,
                    color="#333333", fontweight="bold")

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=7.5, color="#999999")
    ax.grid(color="#CCCCCC", linewidth=0.6, alpha=0.7)
    ax.spines["polar"].set_color("#CCCCCC")

    ax.set_title("朱军《劳动关系认定的理论澄清与规范建构》六维评分\n（法学研究 2023 · 上海市二等奖 · 加权总分 {:.1f}）".format(weighted),
                 fontsize=11.5, fontweight="bold", pad=18)
    fig.text(0.5, 0.02,
             "四模型交叉评审后维度标准差仅 {:.2f}（极度收敛）· 理论建构力 90.2 为六维最高".format(r2_std),
             ha="center", fontsize=8, color="#666666")
    fig.tight_layout()
    out = OUT_DIR / "case_zhujun_sixdim_radar.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"已写出: {out}")


def render_fiveaxis_bar(scores: list[int]) -> None:
    labels = [name for _, name in FIVEAXIS]
    total = sum(scores)

    plt.rcParams.update({
        "font.sans-serif": ["PingFang SC", "Heiti SC", "Arial Unicode MS", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 150,
    })
    fig, ax = plt.subplots(figsize=(8, 3.2))
    y = np.arange(len(labels))
    ax.barh(y, scores, color=ACCENT, alpha=0.85, height=0.55, edgecolor="white")
    for i, s in enumerate(scores):
        ax.text(s - 0.12, i, f"{s}/2", va="center", ha="right",
                fontsize=10, color="white", fontweight="bold")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, 2.4)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["0", "1", "2"], fontsize=8, color="#999999")
    ax.grid(axis="x", linestyle=":", linewidth=0.6, color="#CCCCCC", alpha=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#888888")
    ax.spines["bottom"].set_color("#888888")
    ax.set_title("五轴位置归属度：满分 {}/10（strong）· 两模型 R1+R2 完全一致".format(total),
                 fontsize=11, fontweight="bold", pad=10)
    fig.text(0.5, 0.02,
             "五轴判断「这篇论文产出的知识能否进入中国法学自主知识体系位置结构」，不是第七个质量分",
             ha="center", fontsize=7.5, color="#666666")
    fig.tight_layout()
    out = OUT_DIR / "case_zhujun_fiveaxis_bar.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"已写出: {out}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scores, final_mean, r2_std = load_sixdim()
    weighted = load_master_weighted(1322)
    five = load_fiveaxis()
    print(f"六维 round2_mean: {scores}")
    print(f"round2_final_score_mean={final_mean}  master weighted_score={weighted}  r2_std={r2_std}")
    print(f"五轴 final: {five}  total={sum(five)}")
    render_sixdim_radar(scores, weighted, r2_std)
    render_fiveaxis_bar(five)


if __name__ == "__main__":
    main()
