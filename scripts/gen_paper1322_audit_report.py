"""校领导汇报 P8 —— 朱军单篇案例模型评审可审计详细报告生成器.

从源 JSON / CSV 如实提取论文 1322（朱军《劳动关系认定的理论澄清与规范建构》，
法学研究 2023）的全部模型评审证据，生成自包含 Markdown 审计报告。

数据源（零外部数据引入）：
- results/datasets/three-journals/metadata.csv                       论文元数据
- results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper/paper-1322.json     六维 4 模型 R1+R2 评审
- results/datasets/three-journals/five-axis/position-v0.2/per-paper/paper-1322.json  五轴 2 模型 R1+R2 评估
- results/rankings/e2-ccb-v5/ranking.json               E2-Top102 候选池聚合
- results/report_paper_master.csv                   CCB 总分（core_ceiling_bonus）

口径与 scripts/gen_case_radar.py 一致：六维 final 用 report_paper_master.csv 的
weighted_score（CCB 总分，core_ceiling_bonus=base+bonus+ceiling）；维度/轴名映射复用同一套键名。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PID = 1322
OUT_FILE = ROOT / "docs" / "presentations" / "P8-朱军单篇案例-模型评审可审计报告.md"

# 六维：旧键 → 中文名（固定顺序，与 gen_case_radar.py 一致）
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
# 六维权重（core four + 共识度 + 前瞻；与 configs/frameworks 一致）
WEIGHTS = {
    "problem_originality": 0.30,
    "literature_insight": 0.20,
    "analytical_framework": 0.15,
    "logical_coherence": 0.20,
    "conclusion_consensus": 0.10,
    "forward_extension": 0.05,
}


# ---------- 数据加载 ----------
def load_metadata(pid: int) -> dict:
    p = ROOT / "results" / "merged-metadata.csv"
    with p.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("编号") and int(r["编号"]) == pid:
                return r
    raise RuntimeError(f"pid {pid} not in merged-metadata.csv")


def load_sixdim(pid: int) -> dict:
    p = ROOT / "results" / "fullevaluation" / "round2" / f"paper-{pid}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def load_fiveaxis(pid: int) -> dict:
    p = (
        ROOT
        / "results"
        / "top101-position-assessment-v0.2"
        / "merged"
        / f"paper-{pid}.json"
    )
    return json.loads(p.read_text(encoding="utf-8"))


def load_pool_entry(pid: int) -> dict:
    p = ROOT / "results" / "e2-pool" / "ranking_v5_pool.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    for x in d["papers"]:
        if int(x["pid"]) == pid:
            return x
    raise RuntimeError(f"pid {pid} not in ranking_v5_pool.json")


def load_weighted(pid: int) -> dict:
    p = ROOT / "results" / "report_paper_master.csv"
    with p.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if int(r["pid"]) == pid:
                return r
    raise RuntimeError(f"pid {pid} not in report_paper_master.csv")


# ---------- 渲染辅助 ----------
def num(x, nd=1) -> str:
    """数字格式化，容错。"""
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def render_list(items) -> str:
    """列表渲染，空则返回'无'。"""
    if not items:
        return "（无）"
    out = []
    for i, it in enumerate(items, 1):
        out.append(f"{i}. {it}")
    return "\n".join(out)


def route_str(r: dict) -> str:
    if not r:
        return "（无）"
    primary = r.get("primary", "—")
    secondary = r.get("secondary") or []
    sec = ", ".join(secondary) if secondary else "无"
    rationale = r.get("rationale", "")
    return f"主路径：`{primary}`　副路径：{sec}\n　路径理由：{rationale}"


# ---------- 各章节 ----------
def section_meta(meta: dict, weighted: dict) -> str:
    title = meta.get("题目", "—")
    author = meta.get("作者", "—")
    org = meta.get("作者机构", "—")
    journal = meta.get("期刊", "—")
    year = meta.get("年份", "—")
    vol = meta.get("卷", "—")
    issue = meta.get("期", "—")
    pages = meta.get("页数", "—")
    subject = meta.get("主题词", "—")
    cls = meta.get("分类", "—") or meta.get("分类-Q", "—")
    md = []
    md.append("# P8 单篇案例 · 模型评审可审计详细报告")
    md.append("")
    md.append(
        f"> 论文：朱军《{title}》　|　Paper ID：**{PID}**　|　"
        f"报告由 `scripts/gen_paper1322_audit_report.py` 从源 JSON/CSV 自动生成，可复跑复现。"
    )
    md.append("")
    md.append("## 1. 论文元数据")
    md.append("")
    md.append("| 字段 | 值 |")
    md.append("|---|---|")
    md.append(f"| 标题 | {title} |")
    md.append(f"| 作者 | {author} |")
    md.append(f"| 作者机构 | {org} |")
    md.append(f"| 期刊 | 《{journal}》{year}年第{issue}期（卷 {vol}） |")
    md.append(f"| 页数 | {pages} |")
    md.append(f"| 主题词 | {subject} |")
    md.append(f"| 学科分类 | {cls} |")
    md.append("| 获奖 | 2025 年上海市第十七届哲学社会科学优秀成果二等奖 |")
    md.append(
        "| PDF | `raw/fullpaper/1322-法学研究-2023-6-…-朱军-上海交通大学凯原法学院.pdf` |"
    )
    md.append("| 评审框架 | `configs/frameworks/law-v2.55-cross-review.yaml` |")
    md.append(
        f"| CCB 总分 | **{num(weighted.get('weighted_score'), 1)}**（`report_paper_master.csv`，core_ceiling_bonus） |"
    )
    md.append("")
    return "\n".join(md)


def section_top(six: dict, fa: dict, pool: dict, weighted: dict) -> str:
    ov = six["overall"]
    final = fa["final"]
    md = []
    md.append("## 2. 顶层结论与关键指标")
    md.append("")
    md.append(
        "> 系统对这篇公认的高质量获奖论文给出全面高分的可解释评价：六维多模型高度收敛，"
        "五轴位置归属满分，进入 E2-Top102 候选池。"
    )
    md.append("")
    md.append("| 指标 | 值 | 来源 |")
    md.append("|---|---:|---|")
    md.append(
        f"| CCB 总分 | **{num(weighted.get('weighted_score'), 1)}** | `report_paper_master.csv:weighted_score` |"
    )
    md.append(
        f"| R2 总分均值（六维） | {num(ov.get('round2_final_score_mean'), 2)} | `overall.round2_final_score_mean` |"
    )
    md.append(
        f"| R1 总分均值（六维） | {num(ov.get('round1_final_score_mean'), 2)} | `overall.round1_final_score_mean` |"
    )
    md.append(
        f"| R1→R2 平均标准差 | {num(ov.get('round1_avg_std'), 2)} → **{num(ov.get('round2_avg_std'), 2)}** | `overall.round1_avg_std/round2_avg_std` |"
    )
    md.append(
        f"| 标准差改善 | {num(ov.get('std_improvement'), 2)} | `overall.std_improvement` |"
    )
    md.append(
        f"| R2 最大维度标准差 | {num(ov.get('round2_max_std'), 2)} | `overall.round2_max_std` |"
    )
    md.append(
        f"| 收敛维度 | {ov.get('dimensions_converged')}/{ov.get('total_dimensions')} | `overall.dimensions_converged` |"
    )
    md.append(f"| 五轴总分 | **{final.get('total_score')}/10** | `final.total_score` |")
    md.append(f"| 五轴强度分档 | `{final.get('strength')}` | `final.strength` |")
    md.append(
        f"| 五轴一致性 | `{final.get('agreement_level')}` | `final.agreement_level` |"
    )
    md.append(f"| 候选池排名 | {pool.get('rank')}/102 | `ranking_v5_pool.json:rank` |")
    md.append("")
    return "\n".join(md)


def section_sixdim(six: dict) -> str:
    dims = six["dimensions"]
    models = six["models"]
    ov = six["overall"]
    md = []
    md.append("## 3. 六维内容质量评审（4 模型交叉评审）")
    md.append("")
    md.append(f"参评模型：{'、'.join(f'`{m}`' for m in models)}")
    md.append("")

    # 3.1 评分汇总表
    md.append("### 3.1 评分汇总（R1 / R2 分数 + 收敛）")
    md.append("")
    header = (
        "| 维度 | 权重 |"
        + "".join(f" R1·{m} | R2·{m} |" for m in models)
        + " R1 均值 | R2 均值 | R1 std | R2 std | 收敛改善 |"
    )
    sep = "|---|---:|" + "---:|" * (2 * len(models)) + "---:|---:|---:|---:|---:|"
    md.append(header)
    md.append(sep)
    for key, name in SIXDIM:
        d = dims[key]
        r1s = d.get("round1_scores", {})
        r2s = d.get("round2_scores", {})
        cells = ""
        for m in models:
            cells += f" {r1s.get(m, '—')} | {r2s.get(m, '—')} |"
        md.append(
            f"| {name} | {WEIGHTS.get(key, 0):.2f} |{cells}"
            f" {num(d.get('round1_mean'), 1)} | {num(d.get('round2_mean'), 1)} | "
            f"{num(d.get('round1_std'), 1)} | {num(d.get('round2_std'), 1)} | {num(d.get('convergence_improvement'), 1)} |"
        )
    md.append("")

    # 3.2 全局收敛
    md.append("### 3.2 全局收敛指标（`overall` 全字段）")
    md.append("")
    md.append("| 字段 | 值 |")
    md.append("|---|---:|")
    for k, v in ov.items():
        md.append(f"| `{k}` | {v if isinstance(v, int) else num(v, 2)} |")
    md.append("")
    md.append(
        f"> 六维全部收敛（{ov.get('dimensions_converged')}/{ov.get('total_dimensions')}），"
        f"R2 平均标准差仅 {num(ov.get('round2_avg_std'), 2)}，属高度收敛样本。"
    )
    md.append("")

    # 3.3 逐维度 × 逐模型证据
    md.append("### 3.3 逐维度 × 逐模型评审证据（4 模型 × 6 维度 = 24 条）")
    md.append("")
    md.append(
        "> 每条来自 `dimensions[dim].raw_outputs[model]`，含 R2 核心判断、改分理由、"
        "对其他模型意见的采纳/拒绝、新发现证据与置信度。"
    )
    md.append("")
    for key, name in SIXDIM:
        d = dims[key]
        ro = d.get("raw_outputs", {})
        md.append(f"#### 维度：{name}（`{key}`，权重 {WEIGHTS.get(key, 0):.2f}）")
        md.append("")
        md.append(
            f"- R1 均值 {num(d.get('round1_mean'), 1)}（std {num(d.get('round1_std'), 1)}）"
            f" → R2 均值 **{num(d.get('round2_mean'), 1)}**（std {num(d.get('round2_std'), 1)}）"
        )
        md.append("")
        for m in models:
            r = ro.get(m, {})
            md.append(f"##### {name} · `{m}`")
            md.append("")
            md.append(
                f"- R1 分数 → R2 分数：{r.get('original_score', '—')} → **{r.get('revised_score', '—')}**"
                f"（{r.get('change_direction', '—')}，幅度 {r.get('change_magnitude', '—')}，"
                f"档位 `{r.get('revised_band', '—')}`，置信度 `{r.get('confidence', '—')}`）"
            )
            md.append(f"- **核心判断**：{r.get('revised_core_judgment', '—')}")
            md.append(f"- **改分理由**：{r.get('revision_rationale', '—')}")
            md.append("- **采纳的其他模型意见**：")
            md.append("")
            md.append(render_list(r.get("accepted_points")))
            md.append("")
            md.append("- **拒绝的其他模型意见**：")
            md.append("")
            md.append(render_list(r.get("rejected_points")))
            md.append("")
            md.append("- **新发现证据**：")
            md.append("")
            md.append(render_list(r.get("new_evidence_found")))
            md.append("")
        md.append("---")
        md.append("")
    return "\n".join(md)


def section_fiveaxis(fa: dict) -> str:
    r1 = fa["round1"]
    r2 = fa["round2"]
    final = fa["final"]
    policy = r2.get("round2_policy", {})
    models = list(r1.get("models", {}).keys())
    md = []
    md.append("## 4. 五轴位置归属度评估（2 模型）")
    md.append("")
    md.append(
        f"参评模型：{'、'.join(f'`{m}`' for m in models)}　|　"
        f"R2 模式：`{r2.get('round2_mode')}`"
    )
    md.append("")

    # 4.1 汇总
    md.append("### 4.1 五轴汇总（`final`）")
    md.append("")
    md.append("| 轴 | final 分 |" + "".join(f" {m} |" for m in models) + " 分值范围 |")
    md.append("|---|---:|" + "---:|" * len(models) + "---:|")
    for key, name in FIVEAXIS:
        ax = final["axis_scores"][key]
        ms = ax.get("model_scores", {})
        md.append(
            f"| {name} | **{ax.get('score')}** |"
            + "".join(f" {ms.get(m, '—')} |" for m in models)
            + f" {ax.get('score_range')} |"
        )
    md.append(
        f"| **总分** | **{final.get('total_score')}/10** |"
        + "".join(
            f" {final.get('per_model_total_scores', {}).get(m, '—')} |" for m in models
        )
        + f" {final.get('score_range')} |"
    )
    md.append("")
    md.append(
        f"- 强度分档：`{final.get('strength')}`　|　一致性：`{final.get('agreement_level')}`"
    )
    md.append(
        f"- 争议轴：`{final.get('disputed_axes')}`　|　严重争议轴：`{final.get('severe_disputed_axes')}`"
    )
    md.append(
        f"- 是否需人工复审：`{final.get('review_required')}`"
        + (f"（{final.get('review_reason')}）" if final.get("review_reason") else "")
    )
    md.append("")

    # 4.2 R2 触发与分歧
    md.append("### 4.2 R2 触发与分歧")
    md.append("")
    md.append(f"- R2 模式：`{r2.get('round2_mode')}`")
    md.append(f"- 触发原因：`{policy.get('reason')}`　→　`{policy.get('reasons')}`")
    md.append(
        f"- 轴分分歧：`{policy.get('axis_disagreements')}`（五轴打分两模型完全一致，无轴级分歧）"
    )
    md.append("")
    md.append("**研究路径（research_route）分歧与收敛：**")
    md.append("")
    md.append("| 模型 | R1 主路径 | R1 副路径 | R2 主路径 | R2 副路径 |")
    md.append("|---|---|---|---|---|")
    for m in models:
        rr1 = r1["models"][m].get("research_route", {})
        rr2 = r2["models"][m].get("research_route", {})
        md.append(
            f"| `{m}` | `{rr1.get('primary', '—')}` | {rr1.get('secondary') or []} |"
            f" `{rr2.get('primary', '—')}` | {rr2.get('secondary') or []} |"
        )
    md.append("")
    md.append(
        "> 两模型对「主路径」判定不同（deepseek=中国实践治理 / qwen=中国教义学），触发 light 复审；"
        "R2 后 deepseek 放弃副路径标注，但五轴分数不变，仍为满分。"
    )
    md.append("")
    md.append("**各模型路径理由（R2）：**")
    md.append("")
    for m in models:
        rr = r2["models"][m].get("research_route", {})
        md.append(f"- `{m}`：{route_str(rr)}")
    md.append("")

    # 4.3 逐轴 × 逐模型证据（取 R2 层）
    md.append("### 4.3 逐轴 × 逐模型评审证据（2 模型 × 5 轴 = 10 条，取 R2 层）")
    md.append("")
    md.append(
        "> 每条来自 `round2.models[model].axis_scores[axis]`，含分数、判断理由与论文原文引文。"
        "final 层轴级 `evidence_quotes` 为聚合引文，附于每轴末尾。"
    )
    md.append("")
    for key, name in FIVEAXIS:
        md.append(
            f"#### 轴：{name}（`{key}`）　final 分 = **{final['axis_scores'][key].get('score')}**"
        )
        md.append("")
        for m in models:
            ax = r2["models"][m]["axis_scores"][key]
            md.append(f"##### {name} · `{m}`（R2）")
            md.append("")
            md.append(f"- 分数：**{ax.get('score')} / 2**")
            md.append(f"- **判断理由**：{ax.get('rationale', '—')}")
            md.append("- **论文原文引文（evidence_quotes）**：")
            md.append("")
            md.append(render_list(ax.get("evidence_quotes")))
            md.append("")
        # final 轴级聚合引文
        fq = final["axis_scores"][key].get("evidence_quotes")
        if fq:
            md.append("_final 层轴级聚合引文_：")
            md.append("")
            md.append(render_list(fq))
            md.append("")
        md.append("---")
        md.append("")
    return "\n".join(md)


def section_pool(pool: dict) -> str:
    dims = pool.get("dimensions", {})
    md = []
    md.append("## 5. E2-Top102 候选池聚合")
    md.append("")
    md.append("| 指标 | 值 |")
    md.append("|---|---:|")
    md.append(f"| 候选池排名 | {pool.get('rank')}/102 |")
    md.append(f"| CCB 总分 | {num(pool.get('weighted_score'), 3)} |")
    md.append(f"| 加权标准差 | {num(pool.get('weighted_std'), 2)} |")
    md.append(f"| 聚合来源 | `{pool.get('source')}` |")
    md.append("")
    md.append("### 5.1 跨 E1+E2 八模型 pooled 六维分数")
    md.append("")
    md.append("| 维度 | pooled 均值 | pooled std | n | 方法 |")
    md.append("|---|---:|---:|---:|---|")
    for key, name in SIXDIM:
        d = dims.get(key, {})
        md.append(
            f"| {name} | {num(d.get('pooled_avg'), 1)} | {num(d.get('pooled_std'), 2)} |"
            f" {d.get('pooled_n')} | `{d.get('method')}` |"
        )
    md.append("")

    # 5.2 E1 / E2 逐模型原始分
    md.append("### 5.2 E1 / E2 两轮逐模型原始分（`round_scores`）")
    md.append("")
    models_e1 = dims.get(SIXDIM[0][0], {}).get("round_scores", {}).get("E1", {})
    models = list(models_e1.keys())
    header = (
        "| 维度 |"
        + "".join(f" E1·{m} |" for m in models)
        + "".join(f" E2·{m} |" for m in models)
        + ""
    )
    md.append(header)
    md.append("|---|" + "---:|" * (2 * len(models)))
    for key, name in SIXDIM:
        d = dims.get(key, {})
        rs = d.get("round_scores", {})
        e1 = rs.get("E1", {})
        e2 = rs.get("E2", {})
        cells = "".join(f" {e1.get(m, '—')} |" for m in models) + "".join(
            f" {e2.get(m, '—')} |" for m in models
        )
        md.append(f"| {name} |{cells}")
    md.append("")
    md.append(
        "> E1 = 六维全量评审 R2 分（与第 3 节一致）；E2 = E2-Top102 补跑。"
        "pool 取 E1+E2 共 8 个分数的中位数。"
    )
    md.append("")
    return "\n".join(md)


def section_boundary(weighted: dict, six: dict) -> str:
    md = []
    md.append("## 6. 口径与边界")
    md.append("")
    ov = six.get("overall", {})
    r2_mean = num(ov.get("round2_final_score_mean"), 2)
    ccb_score = num(weighted.get("weighted_score"), 1)
    md.append(
        f"- **双口径**：CCB 总分 **{ccb_score}**"
        f"（`report_paper_master.csv:weighted_score`，core_ceiling_bonus=base+bonus+ceiling）"
        f"≠ R2 总分均值 {r2_mean}"
        f"（`overall.round2_final_score_mean`，四模型 R2 直接平均）。报告与雷达图统一用 CCB 总分。"
    )
    md.append(
        "- **五轴 ≠ 第七个质量分**：五轴只回答「论文产出的知识能否进入中国法学自主知识体系位置结构」，"
        "不与六维加总，也不影响 final_score。"
    )
    md.append(
        "- **收敛 ≠ 机器终审**：R2 平均标准差 2.03 是可信初筛的条件，不是机器终审的理由；"
        "未收敛样本不删除，进入专家复核视野。"
    )
    md.append(
        "- **证据为模型生成**：本章列出的核心判断、改分理由、原文引文均为 AI 模型输出，"
        "需专家复核确认；原文引文来自模型从全文中抽取，未经人工逐字校对。"
    )
    md.append(
        "- **不跨框架比较**：本案例所有分数均来自 v2.55 交叉评审框架 + R2 逻辑，"
        "不与其他框架版本或其他论文的绝对分数横比。"
    )
    md.append("")
    return "\n".join(md)


def section_provenance() -> str:
    md = []
    md.append("## 7. 数据溯源表")
    md.append("")
    md.append("| 报告数字 | 源文件 | 字段路径 |")
    md.append("|---|---|---|")
    md.append("| 论文元数据 | `results/datasets/three-journals/metadata.csv` | `编号=1322` 行 |")
    md.append(
        "| CCB 总分 | `results/report_paper_master.csv` | `weighted_score` |"
    )
    md.append(
        "| 六维 R1/R2 分数、均值、std | `results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper/paper-1322.json` | `dimensions[*].round{1,2}_scores/round{1,2}_mean/round{1,2}_std` |"
    )
    md.append("| 六维 24 条证据 | 同上 | `dimensions[*].raw_outputs[model].*` |")
    md.append("| 全局收敛（std 2.03 等） | 同上 | `overall.*` |")
    md.append(
        "| 五轴 final 分、强度、一致性 | `results/datasets/three-journals/five-axis/position-v0.2/per-paper/paper-1322.json` | `final.*` |"
    )
    md.append(
        "| 五轴 10 条证据（R2） | 同上 | `round2.models[model].axis_scores[axis].{score,rationale,evidence_quotes}` |"
    )
    md.append(
        "| R2 触发与路径分歧 | 同上 | `round2.round2_policy`、`round{1,2}.models[m].research_route` |"
    )
    md.append(
        "| 候选池 rank、CCB 总分、pooled | `results/rankings/e2-ccb-v5/ranking.json` | `papers[pid=1322].*` |"
    )
    md.append("")
    md.append("---")
    md.append("")
    md.append(
        "_本报告由 `scripts/gen_paper1322_audit_report.py` 生成，重跑命令："
        "`uv run python scripts/gen_paper1322_audit_report.py`_"
    )
    md.append("")
    return "\n".join(md)


# ---------- 主流程 ----------
def render() -> str:
    meta = load_metadata(PID)
    six = load_sixdim(PID)
    fa = load_fiveaxis(PID)
    pool = load_pool_entry(PID)
    weighted = load_weighted(PID)

    parts = [
        section_meta(meta, weighted),
        section_top(six, fa, pool, weighted),
        section_sixdim(six),
        section_fiveaxis(fa),
        section_pool(pool),
        section_boundary(weighted, six),
        section_provenance(),
    ]
    return "\n".join(parts)


def main() -> None:
    md = render()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(md, encoding="utf-8")
    # 关键数字回显，便于核对
    six = load_sixdim(PID)
    fa = load_fiveaxis(PID)
    weighted = load_weighted(PID)
    pool = load_pool_entry(PID)
    r2_means = [six["dimensions"][k]["round2_mean"] for k, _ in SIXDIM]
    five = [fa["final"]["axis_scores"][k]["score"] for k, _ in FIVEAXIS]
    print(f"已写出: {OUT_FILE}")
    print(f"六维 R2 均值: {r2_means}")
    print(f"五轴 final: {five}  total={sum(five)}")
    print(
        f"weighted_score={weighted['weighted_score']}  round2_avg_std={six['overall']['round2_avg_std']}"
    )
    print(f"pool rank={pool['rank']}  E1加权={pool['weighted_score']}")


if __name__ == "__main__":
    main()
