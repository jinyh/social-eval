#!/usr/bin/env python3
"""Top 101 论文自主知识信号两轮评估

Round 1 (E1)：deepseek-v4-pro 和 qwen3.6-plus 独立评估
Round 2 (E2)：交叉评审——每个模型看到对方的 R1 评价后重新评分

用法：
    # 全量运行（101 篇）
    python scripts/evaluate_top101_signals_two_rounds.py

    # 只运行 Round 1
    python scripts/evaluate_top101_signals_two_rounds.py --round 1

    # 只运行 Round 2（需要 R1 已完成）
    python scripts/evaluate_top101_signals_two_rounds.py --round 2

    # Dry-run 单篇验证
    python scripts/evaluate_top101_signals_two_rounds.py --dry-run --pid 1510
"""

import argparse
import asyncio
import csv
import glob
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.providers.factory import create_providers
from src.ingestion.parsers.pdf_parser import PDFParser

# ── 配置 ──────────────────────────────────────────────

RANKING_PATH = Path("results/top101/ranking.json")
METADATA_PATH = Path("results/merged-metadata.csv")
FRAMEWORK_PATH = Path("configs/frameworks/law-v2.55-cross-review.yaml")
OUTPUT_DIR = Path("results/top101-signals")

MODELS = ["deepseek-v4-pro", "qwen3.6-plus"]
CONCURRENT_PAPERS = 5
MAX_TEXT_CHARS = 50000

# ── 日志 ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("top101-signals")

# ── 信号量化映射 ─────────────────────────────────────

SIGNAL_MAPPING = {
    "yes": 2, "sufficient": 2, "not_applicable": 2,
    "partial": 1, "uncertain": 1,
    "no": 0, "insufficient": 0,
}


def _signal_score(value: Any) -> int:
    return SIGNAL_MAPPING.get(str(value or "uncertain").strip().lower(), 1)


def _signal_strength(total: int) -> str:
    if total >= 7:
        return "strong"
    if total >= 4:
        return "medium"
    if total >= 1:
        return "weak"
    return "absent"


def _calc_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


# ── 数据加载 ─────────────────────────────────────────

def load_top101() -> list[dict]:
    with open(RANKING_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["papers"]


def load_metadata() -> dict[int, dict]:
    meta: dict[int, dict] = {}
    with open(METADATA_PATH, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            meta[int(row["编号"])] = row
    return meta


def load_framework() -> dict:
    with open(FRAMEWORK_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_pdf(pid: int) -> Path | None:
    matches = glob.glob(f"raw/fullpaper/{pid:04d}-*.pdf")
    return Path(matches[0]) if matches else None


# ── Prompt 构建 ──────────────────────────────────────

def build_r1_prompt(framework: dict, paper_text: str) -> str:
    """构建 Round 1 独立评估 prompt"""
    aks = framework["autonomous_knowledge_signals"]
    prompt_template = aks["prompt_template"]
    output_template = aks["output_template"]
    prompt = prompt_template.replace("{output_template}", output_template)
    return f"{prompt}\n\n论文全文：\n{paper_text[:MAX_TEXT_CHARS]}"


def build_r2_prompt(
    framework: dict,
    paper_text: str,
    self_r1_output: dict,
    other_r1_output: dict,
    model_name: str,
    other_model_name: str,
) -> str:
    """构建 Round 2 交叉评审 prompt"""

    # 格式化 R1 评价
    def fmt_signal_result(output: dict, label: str) -> str:
        scores = output.get("signal_scores", {})
        cpc = output.get("china_problem_centered", "uncertain")
        cpe = output.get("china_practice_explanation_attempted", "uncertain")
        ett = output.get("external_theory_transformation", "uncertain")
        vct = output.get("verifiable_concept_or_thesis", "uncertain")
        total = output.get("autonomous_signal_score", "?")
        strength = output.get("autonomous_signal_strength", "?")
        evidence = output.get("evidence_quotes", [])
        risks = output.get("risks", [])
        special = output.get("involves_special_chinese_institutional_issue", "uncertain")
        trad = output.get("uses_traditional_cultural_resource", "uncertain")

        evidence_str = "\n".join(f"  - {e}" for e in evidence[:3]) if evidence else "  （无）"
        risks_str = ", ".join(risks) if risks else "（无）"

        return f"""【{label}】
信号评分：
  中国问题中心性：{cpc}（{scores.get('china_problem_centered', '?')}分）
  中国实践解释尝试：{cpe}（{scores.get('china_practice_explanation_attempted', '?')}分）
  外部理论转化：{ett}（{scores.get('external_theory_transformation', '?')}分）
  可复核概念或命题：{vct}（{scores.get('verifiable_concept_or_thesis', '?')}分）
总分：{total}/8（{strength}）
涉及中国特殊制度议题：{special}
使用传统文化资源：{trad}
证据引用：
{evidence_str}
识别风险：{risks_str}"""

    self_str = fmt_signal_result(self_r1_output, f"你的第一轮评价（{model_name}）")
    other_str = fmt_signal_result(other_r1_output, f"另一位专家的评价（{other_model_name}）")

    prompt = f"""你是一位法学论文评估专家。你之前对这篇论文进行了【自主知识体系信号校验】，给出了以下评价：

{self_str}

---

另一位评审专家对同一篇论文给出了不同的评价：

{other_str}

---

请你重新阅读论文原文，结合另一位专家的意见，重新审视你的评价。

请仔细思考以下问题：
1. 另一位专家的评价中是否有你之前忽略的合理观点？
2. 重新阅读论文后，你是否发现了之前遗漏的证据或论证？
3. 对于存在分歧的信号维度，哪位专家的判断更准确？

论文正文：
{paper_text[:MAX_TEXT_CHARS]}

---

请重新评估四项核心信号，只输出 JSON，不要输出 Markdown 代码块或额外说明：

{{
  "china_problem_centered": "yes/no/partial/uncertain",
  "china_practice_explanation_attempted": "yes/no/partial/uncertain",
  "external_theory_transformation": "sufficient/partial/insufficient/not_applicable/uncertain",
  "verifiable_concept_or_thesis": "yes/no/partial/uncertain",
  "signal_scores": {{
    "china_problem_centered": 0-2,
    "china_practice_explanation_attempted": 0-2,
    "external_theory_transformation": 0-2,
    "verifiable_concept_or_thesis": 0-2
  }},
  "revised_signal_score": 0-8,
  "revised_signal_strength": "strong/medium/weak/absent",
  "score_changed": true/false,
  "change_details": "说明修改了哪些维度及理由（≤200字）",
  "accepted_points": ["从对方意见中接受的观点"],
  "rejected_points": ["拒绝的观点及理由"],
  "involves_special_chinese_institutional_issue": "yes/no/uncertain",
  "uses_traditional_cultural_resource": "yes/no/uncertain",
  "evidence_quotes": ["原文证据1", "原文证据2"],
  "risks": [],
  "confidence": "high/medium/low"
}}"""
    return prompt


# ── 模型调用 ─────────────────────────────────────────

async def call_model(
    model_name: str,
    prompt: str,
    provider_map: dict,
) -> dict:
    """调用指定模型，返回解析后的 JSON"""
    provider = provider_map.get(model_name)
    if not provider:
        return {"error": f"Provider {model_name} 未找到"}

    try:
        result = await provider.generate_json_response(prompt)

        # 补充缺失字段
        if "signal_scores" not in result:
            result["signal_scores"] = {
                "china_problem_centered": _signal_score(result.get("china_problem_centered")),
                "china_practice_explanation_attempted": _signal_score(result.get("china_practice_explanation_attempted")),
                "external_theory_transformation": _signal_score(result.get("external_theory_transformation")),
                "verifiable_concept_or_thesis": _signal_score(result.get("verifiable_concept_or_thesis")),
            }

        score = result.get("autonomous_signal_score") or result.get("revised_signal_score")
        if score is None:
            score = sum(result["signal_scores"].values())
        result["autonomous_signal_score"] = score
        result["autonomous_signal_strength"] = (
            result.get("revised_signal_strength")
            or result.get("autonomous_signal_strength")
            or _signal_strength(score)
        )

        return result

    except Exception as e:
        logger.error(f"模型 {model_name} 调用失败: {e}")
        return {"error": str(e), "model": model_name}


# ── Round 1 ──────────────────────────────────────────

async def run_round1_paper(
    pid: int,
    pdf_path: Path,
    framework: dict,
    provider_map: dict,
    r1_dir: Path,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """对单篇论文执行 Round 1"""
    output_path = r1_dir / f"paper-{pid}.json"

    # 断点续传
    if output_path.exists():
        logger.info(f"[R1] PID={pid} → 跳过（已完成）")
        with open(output_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async with semaphore:
        logger.info(f"[R1] PID={pid} {pdf_path.stem[:40]} → 开始评估...")
        start = time.time()

        try:
            parser = PDFParser()
            parse_result = parser.parse(str(pdf_path))
            paper_text = parse_result.text
            if not paper_text:
                logger.error(f"[R1] PID={pid} → 无法提取文本")
                return None
        except Exception as e:
            logger.error(f"[R1] PID={pid} → PDF 解析失败: {e}")
            return None

        prompt = build_r1_prompt(framework, paper_text)

        # 2 模型并发
        tasks = [call_model(m, prompt, provider_map) for m in MODELS]
        results = await asyncio.gather(*tasks)

        result: dict = {
            "paper_id": pid,
            "paper": pdf_path.name,
            "timestamp": datetime.now().isoformat(),
            "models": {},
        }
        for model, res in zip(MODELS, results):
            result["models"][model] = res

        # 一致性统计
        valid = [r for r in results if "error" not in r]
        if len(valid) == len(MODELS):
            scores = [r["autonomous_signal_score"] for r in valid]
            result["consistency"] = {
                "scores": scores,
                "mean": sum(scores) / len(scores),
                "std": _calc_std(scores),
                "range": max(scores) - min(scores),
            }

        elapsed = time.time() - start
        result["elapsed_seconds"] = round(elapsed, 1)

        # 保存
        r1_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        score_str = f"{result.get('consistency', {}).get('mean', '?')}"
        logger.info(f"[R1] PID={pid} → 完成 mean={score_str} ({elapsed:.0f}s)")
        return result


# ── Round 2 ──────────────────────────────────────────

async def run_round2_paper(
    pid: int,
    pdf_path: Path,
    r1_result: dict,
    framework: dict,
    provider_map: dict,
    r2_dir: Path,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """对单篇论文执行 Round 2 交叉评审"""
    output_path = r2_dir / f"paper-{pid}.json"

    # 断点续传
    if output_path.exists():
        logger.info(f"[R2] PID={pid} → 跳过（已完成）")
        with open(output_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async with semaphore:
        logger.info(f"[R2] PID={pid} {pdf_path.stem[:40]} → 开始交叉评审...")
        start = time.time()

        # 检查 R1 结果完整性
        r1_models = r1_result.get("models", {})
        if any("error" in r1_models.get(m, {"error": "missing"}) for m in MODELS):
            logger.warning(f"[R2] PID={pid} → R1 结果不完整，跳过 R2")
            return None

        # 提取论文文本（需重新解析）
        try:
            parser = PDFParser()
            parse_result = parser.parse(str(pdf_path))
            paper_text = parse_result.text
            if not paper_text:
                logger.error(f"[R2] PID={pid} → 无法提取文本")
                return None
        except Exception as e:
            logger.error(f"[R2] PID={pid} → PDF 解析失败: {e}")
            return None

        # 构建交叉评审任务
        r2_tasks = []
        for i, model_name in enumerate(MODELS):
            other_model = MODELS[1 - i]  # 对方模型
            self_r1 = r1_models[model_name]
            other_r1 = r1_models[other_model]

            prompt = build_r2_prompt(
                framework=framework,
                paper_text=paper_text,
                self_r1_output=self_r1,
                other_r1_output=other_r1,
                model_name=model_name,
                other_model_name=other_model,
            )
            r2_tasks.append(call_model(model_name, prompt, provider_map))

        r2_results = await asyncio.gather(*r2_tasks)

        result: dict = {
            "paper_id": pid,
            "paper": pdf_path.name,
            "timestamp": datetime.now().isoformat(),
            "models": {},
        }
        for model, res in zip(MODELS, r2_results):
            result["models"][model] = res

        # 一致性统计
        valid = [r for r in r2_results if "error" not in r]
        if len(valid) == len(MODELS):
            scores = [r.get("revised_signal_score") or r.get("autonomous_signal_score", 0) for r in valid]
            result["consistency"] = {
                "scores": scores,
                "mean": sum(scores) / len(scores),
                "std": _calc_std(scores),
                "range": max(scores) - min(scores),
            }

        elapsed = time.time() - start
        result["elapsed_seconds"] = round(elapsed, 1)

        # 保存
        r2_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        score_str = f"{result.get('consistency', {}).get('mean', '?')}"
        logger.info(f"[R2] PID={pid} → 完成 mean={score_str} ({elapsed:.0f}s)")
        return result


# ── 结果合并 ─────────────────────────────────────────

def merge_paper_results(
    pid: int,
    r1_result: dict | None,
    r2_result: dict | None,
    pdf_path: Path,
) -> dict:
    """合并 R1 + R2 为自包含 JSON"""

    merged: dict = {
        "paper_id": pid,
        "paper": pdf_path.name,
        "framework": str(FRAMEWORK_PATH),
        "models": MODELS,
        "round1": None,
        "round2": None,
        "final": None,
    }

    # R1 部分
    if r1_result and "error" not in r1_result:
        r1_models = r1_result.get("models", {})
        r1_scores = []
        r1_per_model = {}
        for m in MODELS:
            m_data = r1_models.get(m, {})
            if "error" not in m_data:
                score = m_data.get("autonomous_signal_score", 0)
                r1_scores.append(score)
                r1_per_model[m] = m_data

        if r1_scores:
            merged["round1"] = {
                **r1_per_model,
                "mean_score": sum(r1_scores) / len(r1_scores),
                "std": _calc_std(r1_scores),
            }

    # R2 部分
    if r2_result and "error" not in r2_result:
        r2_models = r2_result.get("models", {})
        r2_scores = []
        r2_per_model = {}
        for m in MODELS:
            m_data = r2_models.get(m, {})
            if "error" not in m_data:
                score = m_data.get("revised_signal_score") or m_data.get("autonomous_signal_score", 0)
                r2_scores.append(score)
                r2_per_model[m] = m_data

        if r2_scores:
            merged["round2"] = {
                **r2_per_model,
                "mean_score": sum(r2_scores) / len(r2_scores),
                "std": _calc_std(r2_scores),
            }

    # Final 部分：以 R2 为准，R2 缺失则 fallback 到 R1
    source = merged.get("round2") or merged.get("round1")
    if source:
        final_score = source["mean_score"]

        # 逐信号维度均值
        signal_keys = [
            "china_problem_centered",
            "china_practice_explanation_attempted",
            "external_theory_transformation",
            "verifiable_concept_or_thesis",
        ]
        per_signal: dict = {}
        for sk in signal_keys:
            vals: list[float] = []
            for m in MODELS:
                m_data = source.get(m, {})
                ss = m_data.get("signal_scores", {})
                if sk in ss:
                    vals.append(ss[sk])
            per_signal[sk] = {
                "r1_mean": _mean_of_signal(sk, merged.get("round1")),
                "r2_mean": _mean_of_signal(sk, merged.get("round2")),
                "final_mean": sum(vals) / len(vals) if vals else None,
            }

        merged["final"] = {
            "signal_score": final_score,
            "signal_strength": _signal_strength(int(round(final_score))),
            "per_signal": per_signal,
            "convergence_improvement": (
                (merged["round1"]["std"] - merged["round2"]["std"])
                if merged.get("round1") and merged.get("round2")
                else None
            ),
        }

    return merged


def _mean_of_signal(signal_key: str, round_data: dict | None) -> float | None:
    """从 round 数据中提取某个信号维度的模型均值"""
    if not round_data:
        return None
    vals: list[float] = []
    for m in MODELS:
        m_data = round_data.get(m, {})
        if isinstance(m_data, dict):
            ss = m_data.get("signal_scores", {})
            if signal_key in ss:
                vals.append(ss[signal_key])
    return sum(vals) / len(vals) if vals else None


# ── 汇总报告 ─────────────────────────────────────────

def generate_summary(
    papers: list[dict],
    merged_results: list[dict],
    metadata: dict[int, dict],
) -> dict:
    """生成汇总统计"""

    summary: dict = {
        "generated_at": datetime.now().isoformat(),
        "total_papers": len(papers),
        "models": MODELS,
        "framework": str(FRAMEWORK_PATH),
        "completed": 0,
        "r1_only": 0,
        "missing": 0,
        "r1_stats": {},
        "r2_stats": {},
        "final_stats": {},
        "convergence": {},
    }

    r1_scores: list[float] = []
    r2_scores: list[float] = []
    final_scores: list[float] = []
    convergence_improvements: list[float] = []
    strength_dist = {"strong": 0, "medium": 0, "weak": 0, "absent": 0}

    for mr in merged_results:
        if mr.get("final"):
            summary["completed"] += 1
            fs = mr["final"]["signal_score"]
            final_scores.append(fs)
            strength_dist[mr["final"]["signal_strength"]] += 1
        elif mr.get("round1"):
            summary["r1_only"] += 1
        else:
            summary["missing"] += 1

        if mr.get("round1"):
            r1_scores.append(mr["round1"]["mean_score"])
        if mr.get("round2"):
            r2_scores.append(mr["round2"]["mean_score"])
            if mr.get("round1"):
                imp = mr["round1"]["std"] - mr["round2"]["std"]
                convergence_improvements.append(imp)

    if r1_scores:
        summary["r1_stats"] = {
            "count": len(r1_scores),
            "mean": sum(r1_scores) / len(r1_scores),
            "min": min(r1_scores),
            "max": max(r1_scores),
        }
    if r2_scores:
        summary["r2_stats"] = {
            "count": len(r2_scores),
            "mean": sum(r2_scores) / len(r2_scores),
            "min": min(r2_scores),
            "max": max(r2_scores),
        }
    if final_scores:
        summary["final_stats"] = {
            "count": len(final_scores),
            "mean": sum(final_scores) / len(final_scores),
            "min": min(final_scores),
            "max": max(final_scores),
            "strength_distribution": strength_dist,
        }
    if convergence_improvements:
        summary["convergence"] = {
            "count": len(convergence_improvements),
            "mean_improvement": sum(convergence_improvements) / len(convergence_improvements),
            "papers_improved": sum(1 for v in convergence_improvements if v > 0),
        }

    return summary


def generate_report(
    papers: list[dict],
    merged_results: list[dict],
    metadata: dict[int, dict],
    summary: dict,
) -> str:
    """生成 Markdown 报告"""

    lines = [
        "# Top 101 自主知识信号两轮评估报告",
        "",
        f"**生成时间**: {summary['generated_at']}",
        f"**论文总数**: {summary['total_papers']}",
        f"**评测模型**: {', '.join(MODELS)}",
        f"**完成两轮**: {summary['completed']} 篇",
        f"**仅 R1**: {summary['r1_only']} 篇",
        f"**缺失**: {summary['missing']} 篇",
        "",
        "## 统计概览",
        "",
    ]

    if summary.get("r1_stats"):
        s = summary["r1_stats"]
        lines.append(f"### Round 1（独立评估）")
        lines.append(f"- 完成：{s['count']} 篇")
        lines.append(f"- 均值：{s['mean']:.1f}/8")
        lines.append(f"- 范围：{s['min']:.0f} ~ {s['max']:.0f}")
        lines.append("")

    if summary.get("r2_stats"):
        s = summary["r2_stats"]
        lines.append(f"### Round 2（交叉评审）")
        lines.append(f"- 完成：{s['count']} 篇")
        lines.append(f"- 均值：{s['mean']:.1f}/8")
        lines.append(f"- 范围：{s['min']:.0f} ~ {s['max']:.0f}")
        lines.append("")

    if summary.get("convergence"):
        c = summary["convergence"]
        lines.append(f"### 收敛效果")
        lines.append(f"- 平均 std 改善：{c['mean_improvement']:.2f}")
        lines.append(f"- 收敛改善论文数：{c['papers_improved']}/{c['count']}")
        lines.append("")

    if summary.get("final_stats"):
        s = summary["final_stats"]
        lines.append(f"### 最终信号强度分布")
        dist = s["strength_distribution"]
        lines.append(f"- Strong (7-8)：{dist['strong']} 篇")
        lines.append(f"- Medium (4-6)：{dist['medium']} 篇")
        lines.append(f"- Weak (1-3)：{dist['weak']} 篇")
        lines.append(f"- Absent (0)：{dist['absent']} 篇")
        lines.append("")

    # 逐篇表格
    lines.append("## 逐篇结果")
    lines.append("")
    lines.append("| # | PID | 期刊 | 年份 | R1均值 | R1 std | R2均值 | R2 std | 最终 | 强度 | 论文标题 |")
    lines.append("|---|-----|------|------|--------|--------|--------|--------|------|------|----------|")

    for paper_info, mr in zip(papers, merged_results):
        pid = paper_info["pid"]
        rank = paper_info.get("rank", "?")
        m = metadata.get(pid, {})
        title = m.get("题目", "")[:30]
        journal = m.get("期刊", "")
        year = m.get("年份", "")

        r1_mean = f"{mr['round1']['mean_score']:.1f}" if mr.get("round1") else "--"
        r1_std = f"{mr['round1']['std']:.1f}" if mr.get("round1") else "--"
        r2_mean = f"{mr['round2']['mean_score']:.1f}" if mr.get("round2") else "--"
        r2_std = f"{mr['round2']['std']:.1f}" if mr.get("round2") else "--"

        final_score = f"{mr['final']['signal_score']:.1f}" if mr.get("final") else "--"
        final_strength = mr["final"]["signal_strength"] if mr.get("final") else "--"

        lines.append(f"| {rank} | {pid} | {journal} | {year} | {r1_mean} | {r1_std} | {r2_mean} | {r2_std} | {final_score} | {final_strength} | {title} |")

    return "\n".join(lines) + "\n"


# ── 主流程 ───────────────────────────────────────────

async def run_evaluation(
    round_to_run: int | None = None,
    dry_run_pid: int | None = None,
):
    """执行评估主流程"""

    logger.info("=" * 60)
    logger.info("Top 101 自主知识信号两轮评估")
    logger.info(f"模型：{', '.join(MODELS)}")
    logger.info(f"并发：{CONCURRENT_PAPERS} 篇/批次")
    logger.info("=" * 60)

    # 加载数据
    papers = load_top101()
    metadata = load_metadata()
    framework = load_framework()

    logger.info(f"论文总数：{len(papers)}")

    # 创建 providers
    providers = create_providers(MODELS)
    provider_map = {p.model_name: p for p in providers}

    # 目录准备
    r1_dir = OUTPUT_DIR / "round1"
    r2_dir = OUTPUT_DIR / "round2"
    merged_dir = OUTPUT_DIR / "merged"
    for d in [r1_dir, r2_dir, merged_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Dry-run 模式
    if dry_run_pid is not None:
        papers = [p for p in papers if p["pid"] == dry_run_pid]
        if not papers:
            logger.error(f"PID {dry_run_pid} 不在 top101 中")
            return
        logger.info(f"🔬 Dry-run 模式：只评估 PID={dry_run_pid}")

    # 构建论文任务列表
    paper_tasks: list[tuple[int, Path]] = []
    for p in papers:
        pid = p["pid"]
        pdf_path = find_pdf(pid)
        if not pdf_path:
            logger.warning(f"PID={pid}: PDF 未找到，跳过")
            continue
        paper_tasks.append((pid, pdf_path))

    logger.info(f"有效论文：{len(paper_tasks)} 篇")

    semaphore = asyncio.Semaphore(CONCURRENT_PAPERS)

    # ── Round 1 ──
    if round_to_run is None or round_to_run == 1:
        logger.info(f"\n{'─' * 60}")
        logger.info("Round 1：独立评估")
        logger.info(f"{'─' * 60}")

        r1_start = time.time()
        r1_tasks = [
            run_round1_paper(pid, pdf_path, framework, provider_map, r1_dir, semaphore)
            for pid, pdf_path in paper_tasks
        ]
        r1_results = await asyncio.gather(*r1_tasks)
        r1_success = sum(1 for r in r1_results if r is not None)

        r1_elapsed = time.time() - r1_start
        logger.info(
            f"[R1] 完成：{r1_success}/{len(paper_tasks)} 篇 "
            f"({r1_elapsed:.0f}s, {r1_elapsed / max(r1_success, 1):.1f}s/篇)"
        )

    # ── Round 2 ──
    if round_to_run is None or round_to_run == 2:
        logger.info(f"\n{'─' * 60}")
        logger.info("Round 2：交叉评审")
        logger.info(f"{'─' * 60}")

        # 加载所有 R1 结果
        r1_results_map: dict[int, dict] = {}
        for pid, _ in paper_tasks:
            r1_path = r1_dir / f"paper-{pid}.json"
            if r1_path.exists():
                with open(r1_path, "r", encoding="utf-8") as f:
                    r1_results_map[pid] = json.load(f)

        r2_start = time.time()
        r2_tasks = []
        for pid, pdf_path in paper_tasks:
            r1_res = r1_results_map.get(pid)
            if r1_res is None:
                logger.warning(f"[R2] PID={pid}: R1 结果缺失，跳过")
                r2_tasks.append(asyncio.sleep(0, result=None))
                continue
            r2_tasks.append(
                run_round2_paper(pid, pdf_path, r1_res, framework, provider_map, r2_dir, semaphore)
            )

        r2_results = await asyncio.gather(*r2_tasks)
        r2_success = sum(1 for r in r2_results if r is not None)

        r2_elapsed = time.time() - r2_start
        logger.info(
            f"[R2] 完成：{r2_success}/{len(paper_tasks)} 篇 "
            f"({r2_elapsed:.0f}s, {r2_elapsed / max(r2_success, 1):.1f}s/篇)"
        )

    # ── 合并结果 ──
    logger.info(f"\n{'─' * 60}")
    logger.info("合并结果")
    logger.info(f"{'─' * 60}")

    merged_results: list[dict] = []
    for pid, pdf_path in paper_tasks:
        r1_path = r1_dir / f"paper-{pid}.json"
        r2_path = r2_dir / f"paper-{pid}.json"

        r1_res = None
        r2_res = None
        if r1_path.exists():
            with open(r1_path, "r", encoding="utf-8") as f:
                r1_res = json.load(f)
        if r2_path.exists():
            with open(r2_path, "r", encoding="utf-8") as f:
                r2_res = json.load(f)

        merged = merge_paper_results(pid, r1_res, r2_res, pdf_path)
        merged_results.append(merged)

        # 保存 merged
        merged_path = merged_dir / f"paper-{pid}.json"
        with open(merged_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

    # ── 生成汇总 ──
    summary = generate_summary(papers, merged_results, metadata)
    summary_path = OUTPUT_DIR / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # ── 生成报告 ──
    report = generate_report(papers, merged_results, metadata, summary)
    report_path = OUTPUT_DIR / "report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"\n{'=' * 60}")
    logger.info(f"✅ 评估完成")
    logger.info(f"  汇总：{summary_path}")
    logger.info(f"  报告：{report_path}")
    logger.info(f"  Merged：{merged_dir}/ ({len(merged_results)} 篇)")
    logger.info(f"{'=' * 60}")


# ── CLI ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Top 101 自主知识信号两轮评估")
    parser.add_argument(
        "--round", type=int, choices=[1, 2],
        help="只运行指定轮次（1 或 2），默认两轮都运行",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Dry-run 模式：只评估 1 篇论文",
    )
    parser.add_argument(
        "--pid", type=int,
        help="指定 dry-run 的论文 PID（配合 --dry-run 使用）",
    )
    args = parser.parse_args()

    dry_run_pid = args.pid if args.dry_run else None
    if args.dry_run and dry_run_pid is None:
        # 默认用第一篇
        dry_run_pid = 1510

    asyncio.run(run_evaluation(round_to_run=args.round, dry_run_pid=dry_run_pid))


if __name__ == "__main__":
    main()
