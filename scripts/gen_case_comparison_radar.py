"""校领导汇报 PPT —— 朱军 vs 杨清望 六维对照雷达（第5页）.

同框架（v2.55）同源对比，体现区分度：
- 朱军 pid=1322《劳动关系认定的理论澄清与规范建构》final 85.2（高分）
- 杨清望 pid=448《文化法治体系的法理意蕴与实践展开》final 53.3（v2.50.2 已知负样本，v2.55 仍低分）

两篇均在 1920 v2.55 全量评审内，口径一致、可比。
"""

from __future__ import annotations

import json
from math import pi
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "presentations" / "assets"

ZHUJUN = 1322
YANG = 448
SIXDIM = [
    ("problem_originality", "研究创新性"),
    ("literature_insight", "现状洞察度"),
    ("analytical_framework", "理论建构力"),
    ("logical_coherence", "逻辑连贯性"),
    ("conclusion_consensus", "学术共识度"),
    ("forward_extension", "前瞻延展性"),
]
HIGH_COLOR = "#C8102E"   # 朱军 交大红
LOW_COLOR = "#7A8A99"    # 杨清望 中性灰（衬托）


def load(pid: int) -> tuple[list[float], float]:
    f = ROOT / "results" / "fullevaluation" / "round2" / f"paper-{pid}.json"
    d = json.loads(f.read_text())
    dims = d["dimensions"]
    scores = [float(dims[k]["round2_mean"]) for k, _ in SIXDIM]
    final = float(d["overall"]["round2_final_score_mean"])
    return scores, final


def render() -> None:
    s_hi, f_hi = load(ZHUJUN)
    s_lo, f_lo = load(YANG)
    labels = [name for _, name in SIXDIM]
    n = len(labels)
    angles = [i / n * 2 * pi for i in range(n)] + [0]
    hi = s_hi + [s_hi[0]]
    lo = s_lo + [s_lo[0]]

    plt.rcParams.update({
        "font.sans-serif": ["PingFang SC", "Heiti SC", "Arial Unicode MS", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 150,
    })
    fig, ax = plt.subplots(figsize=(8.5, 6.5), subplot_kw=dict(polar=True))
    ax.set_theta_offset(pi / 2)
    ax.set_theta_direction(-1)

    ax.plot(angles, lo, color=LOW_COLOR, linewidth=1.8, linestyle="--")
    ax.fill(angles, lo, color=LOW_COLOR, alpha=0.10)
    ax.plot(angles, hi, color=HIGH_COLOR, linewidth=2.2)
    ax.fill(angles, hi, color=HIGH_COLOR, alpha=0.18)

    for ang, v in zip(angles[:-1], hi[:-1]):
        ax.scatter(ang, v, color=HIGH_COLOR, s=22, zorder=5)
    for ang, v in zip(angles[:-1], lo[:-1]):
        ax.scatter(ang, v, color=LOW_COLOR, s=16, zorder=5)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=7.5, color="#999999")
    ax.grid(color="#CCCCCC", linewidth=0.6, alpha=0.7)
    ax.spines["polar"].set_color("#CCCCCC")

    ax.set_title("同框架（v2.55）六维对照：高分 vs 低分", fontsize=12, fontweight="bold", pad=16)
    legend = [
        Patch(facecolor=HIGH_COLOR, edgecolor=HIGH_COLOR,
              label=f"朱军《劳动关系认定的理论澄清与规范建构》 {f_hi:.1f}"),
        Patch(facecolor=LOW_COLOR, edgecolor=LOW_COLOR,
              label=f"杨清望《文化法治体系的法理意蕴与实践展开》 {f_lo:.1f}"),
    ]
    ax.legend(handles=legend, loc="upper right", bbox_to_anchor=(1.32, 1.12),
              frameon=False, fontsize=8.5)
    fig.text(0.5, 0.015,
             "两篇均出自 1920 篇 v2.55 全量评审 · 同口径可比 · 朱军六维全面领先，唯独前瞻延展性略低",
             ha="center", fontsize=7.5, color="#666666")
    fig.tight_layout()
    out = OUT_DIR / "case_comparison_radar.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"已写出: {out}")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    render()
