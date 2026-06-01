#!/usr/bin/env python3
"""
评测 top30 论文的自主知识信号
使用 DeepSeek v4 pro 和 Qwen3.6-plus 两个模型
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import yaml

# 添加项目根目录到 Python 路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluation.providers.factory import create_providers
from src.ingestion.parsers.pdf_parser import PDFParser

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置
TOP30_DIR = Path("raw/top30_paper")
FRAMEWORK_PATH = Path("configs/frameworks/law-v2.56.6-20260522.yaml")
OUTPUT_DIR = Path("results/top30-signals")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 模型配置
MODELS = [
    "deepseek-v4-pro",
    "qwen3.6-plus"
]

# 并发控制
CONCURRENT_PAPERS = 5  # 每次并发评估 5 篇论文

# 信号量化映射
SIGNAL_MAPPING = {
    "yes": 2,
    "sufficient": 2,
    "not_applicable": 2,
    "partial": 1,
    "uncertain": 1,
    "no": 0,
    "insufficient": 0
}


def load_framework() -> Dict[str, Any]:
    """加载评价框架配置"""
    with open(FRAMEWORK_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


async def extract_text_from_pdf(pdf_path: Path) -> str:
    """从 PDF 提取文本"""
    parser = PDFParser()
    result = parser.parse(str(pdf_path))
    return result.text


async def evaluate_signals_with_model(
    paper_text: str,
    model_name: str,
    prompt: str
) -> Dict[str, Any]:
    """使用指定模型评估自主知识信号"""
    providers = create_providers([model_name])
    provider = providers[0]

    try:
        # 使用 generate_json_response 方法
        result = await provider.generate_json_response(prompt)

        # 计算信号分数（如果模型没有返回）
        if "signal_scores" not in result:
            result["signal_scores"] = {
                "china_problem_centered": SIGNAL_MAPPING.get(
                    result.get("china_problem_centered", "uncertain"), 1
                ),
                "china_practice_explanation_attempted": SIGNAL_MAPPING.get(
                    result.get("china_practice_explanation_attempted", "uncertain"), 1
                ),
                "external_theory_transformation": SIGNAL_MAPPING.get(
                    result.get("external_theory_transformation", "uncertain"), 1
                ),
                "verifiable_concept_or_thesis": SIGNAL_MAPPING.get(
                    result.get("verifiable_concept_or_thesis", "uncertain"), 1
                )
            }

        # 计算总分（如果模型没有返回）
        if "autonomous_signal_score" not in result:
            result["autonomous_signal_score"] = sum(result["signal_scores"].values())

        # 计算信号强度（如果模型没有返回）
        if "autonomous_signal_strength" not in result:
            score = result["autonomous_signal_score"]
            if score >= 7:
                result["autonomous_signal_strength"] = "strong"
            elif score >= 4:
                result["autonomous_signal_strength"] = "medium"
            elif score >= 1:
                result["autonomous_signal_strength"] = "weak"
            else:
                result["autonomous_signal_strength"] = "absent"

        return result

    except Exception as e:
        logger.error(f"模型 {model_name} 评估失败: {e}")
        return {
            "error": str(e),
            "model": model_name
        }


async def evaluate_paper(
    pdf_path: Path,
    framework: Dict[str, Any]
) -> Dict[str, Any]:
    """评估单篇论文的自主知识信号"""
    logger.info(f"开始评估: {pdf_path.name}")

    # 提取文本
    paper_text = await extract_text_from_pdf(pdf_path)
    if not paper_text:
        logger.error(f"无法提取文本: {pdf_path.name}")
        return {
            "paper": pdf_path.name,
            "error": "无法提取文本"
        }

    # 构建 prompt
    signal_config = framework["autonomous_knowledge_signals"]
    prompt_template = signal_config["prompt_template"]
    output_template = signal_config["output_template"]

    prompt = prompt_template.replace("{output_template}", output_template)
    prompt = f"{prompt}\n\n论文全文：\n{paper_text[:50000]}"  # 限制长度

    # 并发评估所有模型
    tasks = [
        evaluate_signals_with_model(paper_text, model, prompt)
        for model in MODELS
    ]
    results = await asyncio.gather(*tasks)

    # 整理结果
    paper_result = {
        "paper": pdf_path.name,
        "timestamp": datetime.now().isoformat(),
        "models": {}
    }

    for model, result in zip(MODELS, results):
        paper_result["models"][model] = result

    # 计算模型间一致性
    if all("error" not in r for r in results):
        scores = [r["autonomous_signal_score"] for r in results]
        paper_result["consistency"] = {
            "scores": scores,
            "mean": sum(scores) / len(scores),
            "std": (sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores)) ** 0.5,
            "range": max(scores) - min(scores)
        }

    logger.info(f"完成评估: {pdf_path.name}")
    return paper_result


async def main():
    """主函数"""
    logger.info("开始评测 top30 论文的自主知识信号")
    logger.info(f"使用模型: {', '.join(MODELS)}")
    logger.info(f"并发数: {CONCURRENT_PAPERS} 篇/批次")

    # 加载框架
    framework = load_framework()
    logger.info(f"加载框架: {framework['metadata']['name']}")

    # 获取所有 PDF 文件
    pdf_files = sorted(TOP30_DIR.glob("*.pdf"))
    logger.info(f"找到 {len(pdf_files)} 篇论文")

    # 分批并发评估
    all_results = []
    for i in range(0, len(pdf_files), CONCURRENT_PAPERS):
        batch = pdf_files[i:i + CONCURRENT_PAPERS]
        logger.info(f"评估批次 {i//CONCURRENT_PAPERS + 1}/{(len(pdf_files)-1)//CONCURRENT_PAPERS + 1}: {len(batch)} 篇")

        # 并发评估当前批次
        batch_tasks = [evaluate_paper(pdf_path, framework) for pdf_path in batch]
        batch_results = await asyncio.gather(*batch_tasks)
        all_results.extend(batch_results)

        # 保存单篇结果
        for pdf_path, result in zip(batch, batch_results):
            output_file = OUTPUT_DIR / f"{pdf_path.stem}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

    # 生成汇总报告
    summary = generate_summary(all_results)

    # 保存汇总结果
    summary_file = OUTPUT_DIR / "summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 生成 Markdown 报告
    report = generate_markdown_report(summary, all_results)
    report_file = OUTPUT_DIR / "report.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)

    logger.info(f"评测完成，结果保存至: {OUTPUT_DIR}")
    logger.info(f"汇总报告: {report_file}")


def generate_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """生成汇总统计"""
    summary = {
        "total_papers": len(results),
        "timestamp": datetime.now().isoformat(),
        "models": MODELS,
        "statistics": {}
    }

    # 按模型统计
    for model in MODELS:
        model_scores = []
        model_strengths = {"strong": 0, "medium": 0, "weak": 0, "absent": 0}

        for result in results:
            if "error" not in result and model in result.get("models", {}):
                model_result = result["models"][model]
                if "error" not in model_result:
                    score = model_result.get("autonomous_signal_score", 0)
                    model_scores.append(score)
                    strength = model_result.get("autonomous_signal_strength", "absent")
                    model_strengths[strength] += 1

        if model_scores:
            summary["statistics"][model] = {
                "count": len(model_scores),
                "mean_score": sum(model_scores) / len(model_scores),
                "min_score": min(model_scores),
                "max_score": max(model_scores),
                "strength_distribution": model_strengths
            }

    # 一致性统计
    consistency_stats = []
    for result in results:
        if "consistency" in result:
            consistency_stats.append(result["consistency"]["std"])

    if consistency_stats:
        summary["consistency"] = {
            "mean_std": sum(consistency_stats) / len(consistency_stats),
            "max_std": max(consistency_stats),
            "min_std": min(consistency_stats)
        }

    return summary


def generate_markdown_report(
    summary: Dict[str, Any],
    results: List[Dict[str, Any]]
) -> str:
    """生成 Markdown 报告"""
    report = f"""# Top30 论文自主知识信号评测报告

**生成时间**: {summary['timestamp']}
**论文数量**: {summary['total_papers']}
**评测模型**: {', '.join(summary['models'])}

## 整体统计

"""

    # 模型统计
    for model, stats in summary.get("statistics", {}).items():
        report += f"""### {model}

- **评测数量**: {stats['count']}
- **平均分数**: {stats['mean_score']:.2f}
- **分数范围**: {stats['min_score']} - {stats['max_score']}
- **信号强度分布**:
  - Strong (7-8分): {stats['strength_distribution']['strong']}
  - Medium (4-6分): {stats['strength_distribution']['medium']}
  - Weak (1-3分): {stats['strength_distribution']['weak']}
  - Absent (0分): {stats['strength_distribution']['absent']}

"""

    # 一致性统计
    if "consistency" in summary:
        report += f"""## 模型一致性

- **平均标准差**: {summary['consistency']['mean_std']:.2f}
- **最大标准差**: {summary['consistency']['max_std']:.2f}
- **最小标准差**: {summary['consistency']['min_std']:.2f}

"""

    # 详细结果表格
    report += """## 详细结果

| 论文 | DeepSeek | Qwen | 平均分 | Std | 一致性 |
|------|----------|------|--------|-----|--------|
"""

    for result in results:
        if "error" in result:
            continue

        paper_name = result["paper"][:50]  # 截断长文件名
        models_data = result.get("models", {})

        deepseek_score = models_data.get("deepseek-v4-pro", {}).get("autonomous_signal_score", "N/A")
        qwen_score = models_data.get("qwen3.6-plus", {}).get("autonomous_signal_score", "N/A")

        if "consistency" in result:
            mean = result["consistency"]["mean"]
            std = result["consistency"]["std"]
            consistency = "✅" if std < 1.0 else "⚠️" if std < 2.0 else "❌"
            report += f"| {paper_name} | {deepseek_score} | {qwen_score} | {mean:.1f} | {std:.2f} | {consistency} |\n"
        else:
            report += f"| {paper_name} | {deepseek_score} | {qwen_score} | - | - | - |\n"

    return report


if __name__ == "__main__":
    asyncio.run(main())
