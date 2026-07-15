"""校领导汇报 PPT —— 三大刊五轴总分 vs 六维加权分 全量分布（上下两面板，1920 篇）.

上=五轴总分(0-10)、下=六维加权分(0-100)，三刊按期刊分色堆叠，带分层计数标注。
布局/字体/无框图例等与 gen_combined_year_trend.py 一致。

数据口径（与趋势图一致，避免混用不可比指标）：
- 五轴：results/datasets/three-journals/five-axis/position-v0.2/summary.csv 的 五轴总分 + 期刊（量尺 0-10）
- 六维：fullevaluation/round2/paper-{id}.json 经 calculate_weighted_total(core_ceiling_bonus)
        重算，按 merged-metadata.csv 的 期刊 分组（与趋势图同算法，非简单均值）
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 非交互后端，适合脚本化出图
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 仓库根上 path
from scripts.gen_journal_year_trend import (  # noqa: E402
    FULL_ROUND2,
    MERGED_META,
    load_scoring_protocol,
    paper_weighted_score,
)

# 三刊固定配色（Okabe-Ito，与 gen_score_histogram.py 一致，CVD-safe）
JOURNAL_COLOR: dict[str, str] = {
    "中国法学": "#0072B2",
    "法学研究": "#E69F00",
    "中国社会科学": "#009E73",
}
JOURNAL_ORDER = list(JOURNAL_COLOR.keys())

ROOT = Path(__file__).resolve().parent.parent
FIVEAXIS_CSV = ROOT / "results" / "fullpaper-5axis-results.csv"
OUT_DIR = ROOT / "docs" / "presentations" / "assets"


def load_fiveaxis_by_journal() -> dict[str, list[float]]:
    by: dict[str, list[float]] = {j: [] for j in JOURNAL_COLOR}
    with FIVEAXIS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            j = r.get("期刊", "").strip()
            s = r.get("五轴总分")
            if j in by and s not in (None, ""):
                try:
                    by[j].append(float(s))
                except ValueError:
                    continue
    return by


def load_sixdim_by_journal(protocol: dict) -> dict[str, list[float]]:
    by: dict[str, list[float]] = {j: [] for j in JOURNAL_COLOR}
    with MERGED_META.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                pid = int(r["编号"])
            except (KeyError, ValueError, TypeError):
                continue
            j = r.get("期刊", "").strip()
            if j not in by:
                continue
            s = paper_weighted_score(FULL_ROUND2 / f"paper-{pid}.json", protocol)
            if s is not None:
                by[j].append(s)
    return by


def draw_hist_panel(
    ax,
    by: dict[str, list[float]],
    bins: list[float],
    xlim: tuple[float, float],
    title: str,
    xlabel: str,
    layer_text: str | None = None,
):
    data = [by[j] for j in JOURNAL_ORDER]
    colors = [JOURNAL_COLOR[j] for j in JOURNAL_ORDER]
    ax.hist(
        data,
        bins=bins,
        stacked=True,
        color=colors,
        edgecolor="white",
        linewidth=0.6,
        label=JOURNAL_ORDER,
        alpha=0.92,
    )
    ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel("论文数", fontsize=12)
    ax.set_xlim(xlim)
    ax.tick_params(axis="both", labelsize=11)
    ax.grid(axis="y", linestyle="--", linewidth=0.4, color="#CCCCCC", alpha=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#AAAAAA")
    ax.spines["bottom"].set_color("#AAAAAA")
    if layer_text:
        ax.text(
            0.02,
            0.97,
            layer_text,
            transform=ax.transAxes,
            fontsize=10,
            va="top",
            ha="left",
            linespacing=1.5,
            bbox=dict(
                boxstyle="round,pad=0.4",
                facecolor="white",
                edgecolor="#DDDDDD",
                linewidth=0.6,
                alpha=0.9,
            ),
        )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    protocol = load_scoring_protocol()

    fa = load_fiveaxis_by_journal()
    sd = load_sixdim_by_journal(protocol)
    for j in JOURNAL_ORDER:
        print(f"[计数] {j}: 五轴 {len(fa[j])} 篇 / 六维 {len(sd[j])} 篇")

    # 五轴分层计数（强≥8 / 中 5-7）
    all5 = [s for j in JOURNAL_ORDER for s in fa[j]]
    strong = sum(1 for s in all5 if s >= 8)
    medium = sum(1 for s in all5 if 5 <= s <= 7)
    fa_layer = (
        f"五轴分层\n"
        f"强（8-10）{strong} 篇\n"
        f"中（5-7） {medium} 篇"
    )

    # 六维分层计数
    all6 = [s for j in JOURNAL_ORDER for s in sd[j]]
    ge80 = sum(1 for s in all6 if s >= 80)
    ge85 = sum(1 for s in all6 if s >= 85)
    ge90 = sum(1 for s in all6 if s >= 90)
    sd_layer = (
        f"六维分层\n"
        f"≥80 分  {ge80} 篇\n≥85 分  {ge85} 篇\n≥90 分  {ge90} 篇"
    )

    plt.rcParams.update(
        {
            "font.sans-serif": [
                "Songti SC",
                "Hiragino Sans GB",
                "PingFang HK",
                "Arial Unicode MS",
                "DejaVu Sans",
            ],
            "axes.unicode_minus": False,
            "figure.dpi": 150,
        }
    )
    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(12, 10.5), gridspec_kw={"hspace": 0.32, "top": 0.92}
    )

    # 大标题
    fig.suptitle(
        "三大刊五轴总分 vs 六维加权分 全量分布比较",
        fontsize=16,
        fontweight="bold",
        y=0.97,
    )

    # 上：五轴总分（0-10，整数 bin）
    draw_hist_panel(
        ax_top,
        fa,
        bins=[i - 0.5 for i in range(12)],
        xlim=(-0.5, 10.5),
        title="五轴总分分布（中国法学自主知识体系位置归属度）",
        xlabel="五轴总分",
        layer_text=fa_layer,
    )
    ax_top.set_xticks(range(0, 11))

    # 下：六维加权分（20-95，步长 5）
    draw_hist_panel(
        ax_bot,
        sd,
        bins=[20 + 5 * i for i in range(16)],
        xlim=(20, 95),
        title="六维加权分分布（创新体系评价）",
        xlabel="六维加权分",
        layer_text=sd_layer,
    )

    # 图例放在上面板内部中间偏上，三刊横排
    ax_top.legend(
        loc="upper center",
        frameon=False,
        fontsize=11,
        ncol=3,
        handletextpad=0.5,
        columnspacing=1.5,
    )

    png = OUT_DIR / "combined_distribution.png"
    svg = OUT_DIR / "combined_distribution.svg"
    fig.savefig(png, dpi=200, bbox_inches="tight", pad_inches=0.3)
    fig.savefig(svg, bbox_inches="tight", pad_inches=0.3)
    print(f"已写出: {png}\n已写出: {svg}")

    # 审计 CSV：score_bin × journal × metric 的篇数
    csv_path = OUT_DIR / "combined_distribution.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "journal", "n", "min", "max", "mean"])
        for j in JOURNAL_ORDER:
            w.writerow(
                [
                    "五轴",
                    j,
                    len(fa[j]),
                    min(fa[j]),
                    max(fa[j]),
                    round(sum(fa[j]) / len(fa[j]), 3),
                ]
            )
        for j in JOURNAL_ORDER:
            w.writerow(
                [
                    "六维",
                    j,
                    len(sd[j]),
                    round(min(sd[j]), 2),
                    round(max(sd[j]), 2),
                    round(sum(sd[j]) / len(sd[j]), 3),
                ]
            )
    print(f"已写出: {csv_path}")


if __name__ == "__main__":
    main()
