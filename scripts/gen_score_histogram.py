"""校领导汇报 PPT —— 三大核心刊 1920 篇论文加权得分分布直方图.

读 results/report_paper_master.csv 的 weighted_score 列，按期刊分色堆叠，
标注朱军案例位置与分层数字，输出 PNG/SVG 到 docs/presentations/assets/。

数据口径：
- 三大核心刊 = 中国法学 / 法学研究 / 中国社会科学（数据集无《中外法学》）
- Paper ID 真源：results/merged-metadata.csv 的「编号」字段；report_paper_master.csv 的 pid 与之一致
- 加权分真源：fullevaluation/round2/paper-{id}.json 的 overall.round2_final_score_mean
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 非交互后端，适合脚本化出图
import matplotlib.pyplot as plt

# 三期刊固定配色（色盲安全，已通过 dataviz validate_palette 校验）
# 固定顺序，不循环：中国法学=蓝、法学研究=橙、中国社会科学=绿
JOURNAL_COLOR: dict[str, str] = {
    "中国法学": "#0072B2",
    "法学研究": "#E69F00",
    "中国社会科学": "#009E73",
}

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "results" / "report_paper_master.csv"
OUT_DIR = ROOT / "docs" / "presentations" / "assets"


def load_rows() -> list[dict[str, str]]:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def to_float(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> None:
    rows = load_rows()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 按期刊分桶
    by_journal: dict[str, list[float]] = {j: [] for j in JOURNAL_COLOR}
    all_scores: list[float] = []
    for r in rows:
        score = to_float(r.get("weighted_score"))
        journal = r.get("journal", "").strip()
        if score is None or journal not in by_journal:
            continue
        by_journal[journal].append(score)
        all_scores.append(score)

    total = len(all_scores)
    ge80 = sum(1 for s in all_scores if s >= 80)
    ge85 = sum(1 for s in all_scores if s >= 85)
    ge88 = sum(1 for s in all_scores if s >= 88)
    print(f"总篇数={total}  ≥80={ge80}  ≥85={ge85}  ≥88={ge88}")

    # 画图
    plt.rcParams.update({
        "font.sans-serif": ["PingFang SC", "Heiti SC", "Arial Unicode MS", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 150,
    })
    fig, ax = plt.subplots(figsize=(11, 5.5))

    bins = [50 + i * 2.5 for i in range(19)]  # 50–95，步长 2.5
    # 固定顺序堆叠
    order = list(JOURNAL_COLOR.keys())
    data = [by_journal[j] for j in order]
    colors = [JOURNAL_COLOR[j] for j in order]
    ax.hist(data, bins=bins, stacked=True, color=colors, edgecolor="white",
            linewidth=0.8, label=[f"{j}（{len(by_journal[j])} 篇）" for j in order])

    # 分层数字标注框
    layer_text = f"分层观察\n≥80 共 {ge80} 篇\n≥85 共 {ge85} 篇\n≥88 共 {ge88} 篇"
    ax.text(0.985, 0.97, layer_text, transform=ax.transAxes,
            fontsize=12, va="top", ha="right",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#F5F5F2",
                      edgecolor="#CCCCCC", linewidth=0.8))

    ax.set_title("三大核心刊 1920 篇论文加权得分分布", fontsize=17, fontweight="bold", pad=14)
    ax.set_xlabel("加权得分", fontsize=14)
    ax.set_ylabel("论文数", fontsize=14)
    ax.tick_params(axis="both", labelsize=11)
    ax.set_xlim(50, 95)
    ax.grid(axis="y", linestyle=":", linewidth=0.6, color="#BBBBBB", alpha=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#888888")
    ax.spines["bottom"].set_color("#888888")

    ax.legend(loc="upper left", frameon=False, fontsize=12)

    fig.tight_layout()
    png = OUT_DIR / "score_histogram_1920.png"
    svg = OUT_DIR / "score_histogram_1920.svg"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    print(f"已写出: {png}\n已写出: {svg}")


if __name__ == "__main__":
    main()
