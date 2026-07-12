"""校领导汇报 PPT —— 年度刊物平均分趋势比较图（2015-2025）.

三条系列：三大刊（合并，不区分具体刊物）、学术月刊（法学版块）、交大法学。
每条画 mean 折线 + P25-P75 IQR 半透明带。输出 PNG/SVG + 审计 CSV。

数据口径（三源统一，避免混用不可比指标）：
- 三源评审结果结构一致（results/{fullevaluation,xueshuyuekan,jiaodafaxue-evaluation}/round2/paper-{id}.json）
- **不混用** report_paper_master.weighted_score（含 E1+E2+E3 合并，另两源无 E2/E3，不可比）
- 统一加权算法：与 src/reporting/builder.py:108 权威路径一致
    dim_means = {dim: mean(dim.round2_scores 各模型分)}
    weighted_score = calculate_weighted_total(dim_means, scoring_protocol)  # core_ceiling_bonus
- 比较区间 2015-2025（交大法学 2026 的 24 篇丢弃）
- 分位带 P25-P75（学术月刊每年 6-18 篇，P10/P90 不稳定）
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
import yaml

from src.reporting.scoring import calculate_weighted_total

# 固定 categorical 色序（Okabe-Ito，已通过 dataviz validate_palette CVD 校验）
# 不随筛选变化：三大刊=蓝、学术月刊=橙、交大法学=绿
GROUP_COLOR: dict[str, str] = {
    "三大刊": "#0072B2",
    "学术月刊（法学版块）": "#E69F00",
    "交大法学": "#009E73",
}
GROUP_ORDER = list(GROUP_COLOR.keys())

ROOT = Path(__file__).resolve().parent.parent
FRAMEWORK_PATH = ROOT / "configs" / "frameworks" / "law-v2.55-cross-review.yaml"
MERGED_META = ROOT / "results" / "merged-metadata.csv"
XUESHU_LIST = ROOT / "results" / "xueshuyuekan" / "paper-list.json"
XUESHU_ROUND2 = ROOT / "results" / "xueshuyuekan" / "round2"
JIAODA_LIST = ROOT / "results" / "jiaodafaxue-paper-list.json"
JIAODA_ROUND2 = ROOT / "results" / "jiaodafaxue-evaluation" / "round2"
FULL_ROUND2 = ROOT / "results" / "fullevaluation" / "round2"
OUT_DIR = ROOT / "docs" / "presentations" / "assets"

YEAR_MIN, YEAR_MAX = 2015, 2025
DIM_KEYS = (
    "problem_originality",
    "literature_insight",
    "analytical_framework",
    "logical_coherence",
    "conclusion_consensus",
    "forward_extension",
)


def load_scoring_protocol() -> dict:
    with FRAMEWORK_PATH.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["scoring_protocol"]


def paper_weighted_score(paper_json: Path, protocol: dict) -> float | None:
    """对单篇 round2 JSON 重算统一加权分（先维均、再 core_ceiling_bonus）。

    与 src/reporting/builder.py:108 的权威路径一致。缺有效分返回 None。
    """
    try:
        with paper_json.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    dims = data.get("dimensions") or {}
    dim_means: dict[str, float] = {}
    for key in DIM_KEYS:
        scores = (dims.get(key) or {}).get("round2_scores") or {}
        vals = [v for v in scores.values() if isinstance(v, (int, float))]
        if not vals:
            return None  # 任一维度缺有效模型分 → 整篇跳过（避免 0 分拖低）
        dim_means[key] = sum(vals) / len(vals)
    return calculate_weighted_total(dim_means, protocol)


def load_three_journals(protocol: dict) -> list[tuple[int, str, float]]:
    """三大刊合并：读 merged-metadata.csv 的 编号/年份，取 fullevaluation round2 分数。"""
    rows: list[tuple[int, str, float]] = []
    with MERGED_META.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                pid = int(r["编号"])
                year = int(r["年份"])
            except (KeyError, ValueError, TypeError):
                continue
            if not (YEAR_MIN <= year <= YEAR_MAX):
                continue
            score = paper_weighted_score(FULL_ROUND2 / f"paper-{pid}.json", protocol)
            if score is None:
                continue
            rows.append((year, "三大刊", score))
    return rows


def load_xueshuyuekan(protocol: dict) -> list[tuple[int, str, float]]:
    """学术月刊（法学版块）：paper-list 自带 year 字段。"""
    with XUESHU_LIST.open("r", encoding="utf-8") as f:
        data = json.load(f)
    rows: list[tuple[int, str, float]] = []
    for p in data.get("papers", []):
        try:
            pid = int(p["id"])
            year = int(p["year"])
        except (KeyError, ValueError, TypeError):
            continue
        if not (YEAR_MIN <= year <= YEAR_MAX):
            continue
        score = paper_weighted_score(XUESHU_ROUND2 / f"paper-{pid}.json", protocol)
        if score is None:
            continue
        rows.append((year, "学术月刊（法学版块）", score))
    return rows


def load_jiaodafaxue(protocol: dict) -> list[tuple[int, str, float]]:
    """交大法学：从文件名正则取年份，丢 2026。"""
    with JIAODA_LIST.open("r", encoding="utf-8") as f:
        data = json.load(f)
    rows: list[tuple[int, str, float]] = []
    for p in data.get("papers", []):
        try:
            pid = int(p["id"])
        except (KeyError, ValueError, TypeError):
            continue
        m = re.search(r"_(\d{4})_交大法学_", p.get("filename", "") or "")
        if not m:
            continue
        year = int(m.group(1))
        if not (YEAR_MIN <= year <= YEAR_MAX):
            continue
        score = paper_weighted_score(JIAODA_ROUND2 / f"paper-{pid}.json", protocol)
        if score is None:
            continue
        rows.append((year, "交大法学", score))
    return rows


def aggregate(rows: list[tuple[int, str, float]]) -> dict[tuple[int, str], dict]:
    """按 (year, group) 聚合 mean/p25/p75/n。"""
    buckets: dict[tuple[int, str], list[float]] = defaultdict(list)
    for year, group, score in rows:
        buckets[(year, group)].append(score)
    out: dict[tuple[int, str], dict] = {}
    for key, vals in buckets.items():
        n = len(vals)
        out[key] = {
            "n": n,
            "mean": statistics.mean(vals),
            "p25": _percentile(vals, 25),
            "p75": _percentile(vals, 75),
        }
    return out


def _percentile(vals: list[float], q: float) -> float:
    """与 numpy.percentile 默认线性插值一致的实现（避免引依赖）。"""
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
    """画一张趋势图；with_band=True 叠加 P25-P75 半透明带，False 只画均值线。"""
    fig, ax = plt.subplots(figsize=(11.5, 6))

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
                mean_y.append(None)
                p25_y.append(None)
                p75_y.append(None)
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
            if mv is not None and 0 < nn < 5:
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
        f"年度刊物平均分趋势比较（2015-2025）{suffix}",
        fontsize=17,
        fontweight="bold",
        pad=14,
    )
    ax.set_xlabel("年份", fontsize=14)
    ax.set_ylabel("加权得分（0-100，core_ceiling_bonus）", fontsize=13)
    ax.set_xticks(years)
    ax.tick_params(axis="both", labelsize=11)
    ax.set_xlim(YEAR_MIN - 0.5, YEAR_MAX + 0.5)
    ax.grid(axis="y", linestyle=":", linewidth=0.6, color="#BBBBBB", alpha=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#888888")
    ax.spines["bottom"].set_color("#888888")

    ax.legend(
        loc="upper left",
        frameon=False,
        fontsize=11,
        ncol=3,
        title="折线=均值" + ("，带=P25-P75" if with_band else ""),
        title_fontsize=10,
    )
    fig.tight_layout()
    return fig


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    protocol = load_scoring_protocol()

    # 数据一致性自检锚点：三大刊 paper-1 重算分应 ≈ report_paper_master 82.725
    anchor = paper_weighted_score(FULL_ROUND2 / "paper-1.json", protocol)
    print(
        f"[自检] 三大刊 paper-1 重算加权分 = {anchor}（对照 report_paper_master 82.725，量级一致即可）"
    )

    rows: list[tuple[int, str, float]] = []
    rows += load_three_journals(protocol)
    rows += load_xueshuyuekan(protocol)
    rows += load_jiaodafaxue(protocol)

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
    png = OUT_DIR / "journal_year_score_trend.png"
    svg = OUT_DIR / "journal_year_score_trend.svg"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    print(f"已写出: {png}\n已写出: {svg}")
    plt.close(fig)

    # 图2：仅均值线，无分位带
    fig2 = plot_figure(agg, years, with_band=False)
    png2 = OUT_DIR / "journal_year_score_trend_mean_only.png"
    svg2 = OUT_DIR / "journal_year_score_trend_mean_only.svg"
    fig2.savefig(png2, dpi=200, bbox_inches="tight")
    fig2.savefig(svg2, bbox_inches="tight")
    print(f"已写出: {png2}\n已写出: {svg2}")
    plt.close(fig2)

    # 审计 CSV
    csv_path = OUT_DIR / "journal_year_score_trend.csv"
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
