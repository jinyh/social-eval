"""校领导汇报 PPT —— 五轴总分平均分年度趋势图（2015-2025）.

三条系列：三大刊（合并，不区分具体刊物）、学术月刊（法学版块）、交大法学。
每条画 mean 折线（+ 可选 P25-P75 IQR 带）。输出 PNG/SVG + 审计 CSV。

数据口径（三源五轴 total_score，量尺 0-10，每轴 0-2）：
- 三大刊：五轴 summary.csv 与 metadata.csv 按 paper_id 关联
- 交大法学：results/datasets/jiaodafaxue/five-axis/position-v0.2/per-paper/paper-{id}.json → final.total_score
          年份从 paper 文件名（含“_YYYY_交大法学_”）正则提取
- 学术月刊：规范数据集五轴 per-paper 结果，年份从论文路径提取
- 比较区间 2015-2025（交大 2026 丢弃）
- 三源五轴全量覆盖、同量尺，口径一致可比
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 非交互后端，适合脚本化出图
import matplotlib.pyplot as plt

# 固定 categorical 色序（Okabe-Ito，与六维趋势图一致，CVD-safe）
GROUP_COLOR: dict[str, str] = {
    "三大刊": "#0072B2",
    "学术月刊（法学版块）": "#E69F00",
    "交大法学": "#009E73",
}
GROUP_ORDER = list(GROUP_COLOR.keys())

ROOT = Path(__file__).resolve().parent.parent
THREE_BASE = ROOT / "results" / "datasets" / "three-journals"
FIVEAXIS_CSV = THREE_BASE / "five-axis" / "position-v0.2" / "summary.csv"
THREE_METADATA = THREE_BASE / "metadata.csv"
JIAODA_MERGED = ROOT / "results" / "datasets" / "jiaodafaxue" / "five-axis" / "position-v0.2" / "per-paper"
XUESHU_MERGED = ROOT / "results" / "datasets" / "xueshuyuekan" / "five-axis" / "position-v0.2" / "per-paper"
OUT_DIR = ROOT / "docs" / "presentations" / "assets"

YEAR_MIN, YEAR_MAX = 2015, 2025


def load_three_journals() -> list[tuple[int, str, float]]:
    """三大刊合并：五轴摘要与权威元数据按 paper_id 关联。"""
    rows: list[tuple[int, str, float]] = []
    with THREE_METADATA.open("r", encoding="utf-8-sig", newline="") as f:
        years = {int(r["编号"]): int(r["年份"]) for r in csv.DictReader(f)}
    with FIVEAXIS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                year = years[int(r["paper_id"])]
                score = float(r["五轴总分"])
            except (KeyError, ValueError, TypeError):
                continue
            if not (YEAR_MIN <= year <= YEAR_MAX):
                continue
            rows.append((year, "三大刊", score))
    return rows


def load_jiaodafaxue() -> list[tuple[int, str, float]]:
    """交大法学：遍历 merged JSON 取 final.total_score，年份从文件名正则。"""
    rows: list[tuple[int, str, float]] = []
    if not JIAODA_MERGED.exists():
        print(f"[警告] {JIAODA_MERGED} 不存在，跳过交大法学")
        return rows
    for p in sorted(JIAODA_MERGED.glob("paper-*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        score = (data.get("final") or {}).get("total_score")
        if score is None:
            continue
        m = re.search(r"_(\d{4})_交大法学_", data.get("paper", "") or "")
        if not m:
            continue
        year = int(m.group(1))
        if not (YEAR_MIN <= year <= YEAR_MAX):
            continue
        rows.append((year, "交大法学", float(score)))
    return rows


def load_xueshuyuekan() -> list[tuple[int, str, float]]:
    """学术月刊：遍历五轴 JSON，从论文路径提取年份。"""
    rows: list[tuple[int, str, float]] = []
    if not XUESHU_MERGED.exists():
        print("[警告] 学术月刊五轴结果不存在，跳过学术月刊")
        return rows
    for p in sorted(XUESHU_MERGED.glob("paper-*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        score = (data.get("final") or {}).get("total_score")
        if score is None:
            continue
        m2 = re.search(r"_(\d{4})_学术月刊_", data.get("paper", "") or "")
        if not m2:
            continue
        year = int(m2.group(1))
        if not (YEAR_MIN <= year <= YEAR_MAX):
            continue
        rows.append((year, "学术月刊（法学版块）", float(score)))
    return rows


def aggregate(rows: list[tuple[int, str, float]]) -> dict[tuple[int, str], dict]:
    """按 (year, group) 聚合 mean/p25/p75/n。"""
    buckets: dict[tuple[int, str], list[float]] = defaultdict(list)
    for year, group, score in rows:
        buckets[(year, group)].append(score)
    out: dict[tuple[int, str], dict] = {}
    for key, vals in buckets.items():
        out[key] = {
            "n": len(vals),
            "mean": statistics.mean(vals),
            "p25": _percentile(vals, 25),
            "p75": _percentile(vals, 75),
        }
    return out


def _percentile(vals: list[float], q: float) -> float:
    """与 numpy.percentile 默认线性插值一致（避免引依赖）。"""
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * (q / 100.0)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def plot_figure(
    agg: dict[tuple[int, str], dict], years: list[int], with_band: bool
) -> matplotlib.figure.Figure:
    """画一张趋势图；with_band=True 叠加 P25-P75 带，False 只画均值线。"""
    fig, ax = plt.subplots(figsize=(11.5, 6))

    nan = float("nan")
    for group in GROUP_ORDER:
        color = GROUP_COLOR[group]
        mean_y, p25_y, p75_y, ns = [], [], [], []
        for y in years:
            stat = agg.get((y, group))
            if stat:
                mean_y.append(stat["mean"])
                p25_y.append(stat["p25"])
                p75_y.append(stat["p75"])
                ns.append(stat["n"])
            else:
                mean_y.append(nan)
                p25_y.append(nan)
                p75_y.append(nan)
                ns.append(0)

        if with_band:
            ax.fill_between(
                years, p25_y, p75_y, color=color, alpha=0.18, linewidth=0, zorder=2
            )
        ax.plot(
            years,
            mean_y,
            color=color,
            linewidth=2.2,
            marker="o",
            markersize=5,
            label=f"{group}",
            zorder=3,
        )
        # 小样本（n<5）在点旁标注 n
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

    suffix = "（含 P25-P75 分位带）" if with_band else "（均值线）"
    ax.set_title(
        f"五轴总分年度趋势比较（2015-2025）{suffix}",
        fontsize=17,
        fontweight="bold",
        pad=14,
    )
    ax.set_xlabel("年份", fontsize=14)
    ax.set_ylabel("五轴总分（0-10，中国法学自主知识体系位置归属度）", fontsize=12)
    ax.set_xticks(years)
    ax.tick_params(axis="both", labelsize=11)
    ax.set_xlim(YEAR_MIN - 0.5, YEAR_MAX + 0.5)
    ax.set_ylim(0, 10)
    ax.grid(axis="y", linestyle=":", linewidth=0.6, color="#BBBBBB", alpha=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#888888")
    ax.spines["bottom"].set_color("#888888")

    ax.legend(
        loc="lower left",
        frameon=True,
        fancybox=False,
        edgecolor="#CCCCCC",
        fontsize=11,
        ncol=3,
    )
    fig.tight_layout()
    return fig


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[int, str, float]] = []
    rows += load_three_journals()
    rows += load_xueshuyuekan()
    rows += load_jiaodafaxue()

    agg = aggregate(rows)
    for g in GROUP_ORDER:
        n = sum(v["n"] for (y, gg), v in agg.items() if gg == g)
        print(f"[计数] {g}（2015-2025）共 {n} 篇")

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

    # 图1：均值 + P25-P75 分位带
    fig = plot_figure(agg, years, with_band=True)
    png = OUT_DIR / "fiveaxis_year_score_trend.png"
    svg = OUT_DIR / "fiveaxis_year_score_trend.svg"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    print(f"已写出: {png}\n已写出: {svg}")
    plt.close(fig)

    # 图2：仅均值线，无分位带
    fig2 = plot_figure(agg, years, with_band=False)
    png2 = OUT_DIR / "fiveaxis_year_score_trend_mean_only.png"
    svg2 = OUT_DIR / "fiveaxis_year_score_trend_mean_only.svg"
    fig2.savefig(png2, dpi=200, bbox_inches="tight")
    fig2.savefig(svg2, bbox_inches="tight")
    print(f"已写出: {png2}\n已写出: {svg2}")
    plt.close(fig2)

    # 审计 CSV
    csv_path = OUT_DIR / "fiveaxis_year_score_trend.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "group", "n", "mean", "p25", "p75"])
        for y in years:
            for g in GROUP_ORDER:
                stat = agg.get((y, g))
                if stat:
                    w.writerow(
                        [
                            y,
                            g,
                            stat["n"],
                            round(stat["mean"], 3),
                            round(stat["p25"], 3),
                            round(stat["p75"], 3),
                        ]
                    )
    print(f"已写出: {csv_path}")


if __name__ == "__main__":
    main()
