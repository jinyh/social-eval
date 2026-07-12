"""校领导汇报 PPT —— 三大核心刊 1920 篇论文五轴总分分布直方图.

与 gen_score_histogram.py 配对：六维加权分用前者（质量评价），五轴总分用本脚本
（中国自主知识体系位置归属度）。样式严格对齐，仅分箱/量纲/观察框位置按五轴特性调整。

读 results/report_paper_master.csv 的 pid+journal，按 pid 加载五轴聚合总分，
按期刊分色堆叠，标注分层观察数字，输出 PNG/SVG 到 docs/presentations/assets/。

数据口径：
- 五轴总分真源：fullpaper-position-assessment-stage0/round2/paper-{pid}.json 的 aggregate_preview.total_score
  （0–10 整数，deepseek-v4-pro + qwen3.6-plus 两模型 R2 条件收敛聚合）
- 期刊关联：report_paper_master.csv 的 pid（与 merged-metadata.csv 编号一致）+ journal
- 三大核心刊 = 中国法学 / 法学研究 / 中国社会科学（数据集无《中外法学》）
- 6 篇全拒论文无五轴聚合，自动跳过
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 非交互后端，适合脚本化出图
import matplotlib.pyplot as plt

# 三期刊固定配色（色盲安全，与 gen_score_histogram.py 完全一致）
JOURNAL_COLOR: dict[str, str] = {
    "中国法学": "#0072B2",
    "法学研究": "#E69F00",
    "中国社会科学": "#009E73",
}

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "results" / "report_paper_master.csv"
FIVEAXIS_DIR = ROOT / "results" / "fullpaper-position-assessment-stage0" / "round2"
OUT_DIR = ROOT / "docs" / "presentations" / "assets"


def load_rows() -> list[dict[str, str]]:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fiveaxis_total(pid: int) -> int | None:
    """取某篇论文的五轴聚合总分（0–10）。无文件或无聚合返回 None。"""
    p = FIVEAXIS_DIR / f"paper-{pid}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    ap = d.get("aggregate_preview") or {}
    return ap.get("total_score")


def main() -> None:
    rows = load_rows()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 按期刊分桶
    by_journal: dict[str, list[int]] = {j: [] for j in JOURNAL_COLOR}
    all_scores: list[int] = []
    for r in rows:
        try:
            pid = int(r.get("pid", ""))
        except ValueError:
            continue
        journal = r.get("journal", "").strip()
        if journal not in by_journal:
            continue
        score = fiveaxis_total(pid)
        if score is None:
            continue
        by_journal[journal].append(score)
        all_scores.append(score)

    total = len(all_scores)
    full = sum(1 for s in all_scores if s == 10)
    ge9 = sum(1 for s in all_scores if s >= 9)
    strong = sum(1 for s in all_scores if 8 <= s <= 10)
    lt8 = sum(1 for s in all_scores if s < 8)
    hidden = sum(1 for s in all_scores if s < 6)  # x 轴从 6 起裁掉的篇数
    mean = sum(all_scores) / total if total else 0
    print(f"总篇数={total}  满分10={full}  ≥9={ge9}  strong(8-10)={strong}  <8={lt8}  0-5未显示={hidden}  均值={mean:.3f}")

    # 画图
    plt.rcParams.update({
        "font.sans-serif": ["PingFang SC", "Heiti SC", "Arial Unicode MS", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 150,
    })
    fig, ax = plt.subplots(figsize=(11, 5.5))

    bins = list(range(0, 12))  # 0–10，步长 1（全部入桶，x 轴再裁到 6 起展示）
    order = list(JOURNAL_COLOR.keys())
    data = [by_journal[j] for j in order]
    colors = [JOURNAL_COLOR[j] for j in order]
    ax.hist(
        data, bins=bins, stacked=True, color=colors, edgecolor="white",
        linewidth=0.8, label=[f"{j}（{len(by_journal[j])} 篇）" for j in order],
    )

    # 每根柱顶标总数（矮柱也能读数）
    totals_by_score: dict[int, int] = {}
    for s in all_scores:
        totals_by_score[s] = totals_by_score.get(s, 0) + 1
    for score in range(6, 11):
        cnt = totals_by_score.get(score, 0)
        if cnt:
            ax.text(score, cnt + 25, f"{cnt}", ha="center", va="bottom",
                    fontsize=11, color="#444444", fontweight="bold")

    # 分层数字标注框（满分柱在最右，左上为空旷区，不遮挡任何柱）
    layer_text = (
        "分层观察\n"
        f"满分10 共 {full} 篇\n"
        f"≥9 共 {ge9} 篇\n"
        f"strong(8–10) 共 {strong} 篇\n"
        f"<8 共 {lt8} 篇\n"
        f"0–5分 共 {hidden} 篇（未显示）"
    )
    ax.text(0.015, 0.965, layer_text, transform=ax.transAxes,
            fontsize=11.5, va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#F5F5F2",
                      edgecolor="#CCCCCC", linewidth=0.8))

    ax.set_title("三大核心刊 1920 篇论文五轴总分分布", fontsize=17, fontweight="bold", pad=14)
    ax.set_xlabel("五轴总分（中国自主知识体系位置归属度，0–10）", fontsize=14)
    ax.set_ylabel("论文数", fontsize=14)
    ax.set_xticks(range(6, 11))
    ax.tick_params(axis="both", labelsize=11)
    ax.set_xlim(5.5, 10.5)  # x 轴从 6 起展示，0–5 矮柱裁掉
    ax.set_ylim(0, 1650)  # 留出柱顶数字呼吸空间
    ax.grid(axis="y", linestyle=":", linewidth=0.6, color="#BBBBBB", alpha=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#888888")
    ax.spines["bottom"].set_color("#888888")

    ax.legend(loc="upper center", bbox_to_anchor=(0.52, 0.98),
              ncol=3, frameon=False, fontsize=12)

    fig.tight_layout()
    png = OUT_DIR / "fiveaxis_histogram_1920.png"
    svg = OUT_DIR / "fiveaxis_histogram_1920.svg"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    print(f"已写出: {png}\n已写出: {svg}")


if __name__ == "__main__":
    main()
