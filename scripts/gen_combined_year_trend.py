"""校领导汇报 PPT —— 五轴总分 vs 六维加权分 年度趋势合并图（小多图分面，2015-2025）.

一张图、上下两面板共享 x 轴：上=五轴总分(0-10)，下=六维加权分(0-100)。
每面板 3 条 mean 折线（三大刊/学术月刊/交大法学），配色一致、共享图例。
采用小多图分面而非双纵轴（双纵轴是 dataviz 头号反模式：两量纲并置刻度对应人为、
易制造虚假相关、6 线拥挤）。

复用两个现有脚本的 loader（零重复加载逻辑）：
- 五轴：scripts/gen_fiveaxis_year_trend.py（三大刊 CSV + 交大/学术 merged JSON）
- 六维：scripts/gen_journal_year_trend.py（fullevaluation round2 + 交大/学术 round2，
        经 calculate_weighted_total 统一重算 core_ceiling_bonus）
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 非交互后端，适合脚本化出图
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 仓库根上 path
from scripts.gen_fiveaxis_year_trend import (  # noqa: E402
    GROUP_COLOR,
    GROUP_ORDER,
    aggregate,
    load_jiaodafaxue as fa_jiaoda,
    load_three_journals as fa_three,
    load_xueshuyuekan as fa_xueshu,
)
from scripts.gen_journal_year_trend import (  # noqa: E402
    load_jiaodafaxue as sd_jiaoda,
    load_scoring_protocol,
    load_three_journals as sd_three,
    load_xueshuyuekan as sd_xueshu,
)

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "presentations" / "assets"
YEAR_MIN, YEAR_MAX = 2015, 2025


def draw_panel(
    ax,
    agg: dict,
    years: list[int],
    ylim_top: float,
    ylabel: str,
    title: str,
    annotate_n: bool = True,
):
    """在一个 axes 上画 3 系列 mean 折线，返回图例 handles/labels。"""
    nan = float("nan")
    handles = []
    for group in GROUP_ORDER:
        color = GROUP_COLOR[group]
        mean_y, ns = [], []
        for y in years:
            stat = agg.get((y, group))
            if stat:
                mean_y.append(stat["mean"])
                ns.append(stat["n"])
            else:
                mean_y.append(nan)
                ns.append(0)
        (line,) = ax.plot(
            years,
            mean_y,
            color=color,
            linewidth=2.2,
            marker="o",
            markersize=5,
            label=group,
            zorder=3,
        )
        handles.append(line)
        if annotate_n:
            for x, mv, nn in zip(years, mean_y, ns):
                if mv == mv and 0 < nn < 5:  # mv==mv 排除 NaN
                    ax.annotate(
                        f"n={nn}",
                        (x, mv),
                        textcoords="offset points",
                        xytext=(0, 7),
                        fontsize=8,
                        color=color,
                        ha="center",
                    )

    ax.set_title(title, fontsize=13, fontweight="bold", pad=8)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_ylim(0, ylim_top)
    ax.set_xlim(YEAR_MIN - 0.5, YEAR_MAX + 0.5)
    ax.grid(axis="y", linestyle=":", linewidth=0.6, color="#BBBBBB", alpha=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=11)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#888888")
    ax.spines["bottom"].set_color("#888888")
    return handles, GROUP_ORDER


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    protocol = load_scoring_protocol()

    rows_5 = fa_three() + fa_xueshu() + fa_jiaoda()
    rows_6 = sd_three(protocol) + sd_xueshu(protocol) + sd_jiaoda(protocol)
    agg5 = aggregate(rows_5)
    agg6 = aggregate(rows_6)

    for g in GROUP_ORDER:
        n5 = sum(v["n"] for (y, gg), v in agg5.items() if gg == g)
        n6 = sum(v["n"] for (y, gg), v in agg6.items() if gg == g)
        print(f"[计数] {g}: 五轴 {n5} 篇 / 六维 {n6} 篇")

    years = list(range(YEAR_MIN, YEAR_MAX + 1))

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
    fig, (ax5, ax6) = plt.subplots(
        2, 1, figsize=(11.5, 8.5), sharex=True, constrained_layout=True
    )

    draw_panel(
        ax5,
        agg5,
        years,
        ylim_top=10,
        ylabel="五轴总分（0-10，位置归属度）",
        title="五轴总分（中国法学自主知识体系位置归属度）",
    )
    draw_panel(
        ax6,
        agg6,
        years,
        ylim_top=100,
        ylabel="六维加权分（0-100，论文质量）",
        title="六维加权分（创新体系评价）",
    )
    ax6.set_xlabel("年份", fontsize=14)
    ax6.set_xticks(years)

    # 共享图例：取 ax5 的 handles，放上面板底部居中（y<3.5 一带为空），无框，标签缩短
    handles, _ = ax5.get_legend_handles_labels()
    short_labels = ["三大刊", "学术月刊", "交大法学"]
    ax5.legend(
        handles=handles,
        labels=short_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.02),
        frameon=False,
        fontsize=11,
        ncol=3,
        handletextpad=0.5,
        columnspacing=1.6,
    )

    fig.suptitle(
        "五轴总分 vs 六维加权分 年度趋势比较（2015-2025）",
        fontsize=17,
        fontweight="bold",
    )

    png = OUT_DIR / "combined_year_score_trend.png"
    svg = OUT_DIR / "combined_year_score_trend.svg"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    print(f"已写出: {png}\n已写出: {svg}")

    # 审计 CSV：year/group/n/mean_5axis/mean_6dim
    csv_path = OUT_DIR / "combined_year_score_trend.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "group", "n_5axis", "mean_5axis", "n_6dim", "mean_6dim"])
        for y in years:
            for g in GROUP_ORDER:
                s5 = agg5.get((y, g))
                s6 = agg6.get((y, g))
                if s5 or s6:
                    w.writerow(
                        [
                            y,
                            g,
                            s5["n"] if s5 else "",
                            round(s5["mean"], 3) if s5 else "",
                            s6["n"] if s6 else "",
                            round(s6["mean"], 3) if s6 else "",
                        ]
                    )
    print(f"已写出: {csv_path}")


if __name__ == "__main__":
    main()
