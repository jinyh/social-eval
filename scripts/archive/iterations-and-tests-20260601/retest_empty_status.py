#!/usr/bin/env python3
"""
补测 Phase 2 Round 1 空状态论文

对 90 篇空状态论文的空状态模型重新运行评审，并将结果合并回原始文件。

用法：
    # 正常运行
    python scripts/retest_empty_status.py \
        --error-summary results/phase2-evaluation/round1-err/error-summary.json \
        --round1-dir results/phase2-evaluation/round1 \
        --framework configs/frameworks/law-v2.55-cross-review.yaml \
        --concurrency 3

    # 模拟运行（不调用 API）
    python scripts/retest_empty_status.py \
        --error-summary results/phase2-evaluation/round1-err/error-summary.json \
        --round1-dir results/phase2-evaluation/round1 \
        --dry-run
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_convergence_test import run_convergence_test
from src.ingestion.preprocessor import process_file


def setup_logging(output_dir: Path) -> logging.Logger:
    """配置日志"""
    log_file = output_dir / "retest-execution.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    return logger


def load_empty_status_papers(error_summary_path: Path) -> List[Dict[str, Any]]:
    """加载空状态论文清单"""
    with open(error_summary_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    empty_status_papers = data.get('papers', {}).get('1-empty-status', [])

    logger.info(f"加载空状态论文: {len(empty_status_papers)} 篇")

    return empty_status_papers


def build_retest_tasks(empty_status_papers: List[Dict], round1_dir: Path, base_dir: Path) -> List[Dict]:
    """构建补测任务列表"""
    tasks = []

    for paper in empty_status_papers:
        paper_id = paper['paper_id']
        paper_name = paper['paper_name']
        empty_models = paper['empty_models']

        # 原始结果文件路径
        original_result_path = round1_dir / f"{paper_id}.json"

        if not original_result_path.exists():
            logger.warning(f"{paper_id}: 原始结果文件不存在，跳过")
            continue

        # 论文文件路径（从 paper_name 提取）
        paper_path = base_dir / paper_name

        if not paper_path.exists():
            logger.warning(f"{paper_id}: 论文文件不存在 - {paper_path}")
            continue

        tasks.append({
            'paper_id': paper_id,
            'paper_path': str(paper_path),
            'empty_models': empty_models,
            'original_result_path': original_result_path
        })

    logger.info(f"构建补测任务: {len(tasks)} 篇")

    return tasks


def is_already_retested(original_result: Dict, empty_models: List[str]) -> bool:
    """检查是否已经补测过"""
    precheck = original_result.get('precheck', {})

    for model in empty_models:
        model_result = precheck.get(model, {})
        if isinstance(model_result, dict):
            status = model_result.get('status', '')
            conclusion = model_result.get('conclusion', '')
            # 如果仍然是空状态，说明未补测
            if status == '' and conclusion == '':
                return False

    # 所有空状态模型都已填充
    return True


async def retest_paper_models(
    paper_path: str,
    empty_models: List[str],
    framework_path: str,
    logger: logging.Logger
) -> Dict[str, Any]:
    """
    对空状态模型重新运行评审

    返回：
    {
        'success': True/False,
        'results': {
            'model_name': {
                'precheck': {...},
                'dimensions': {...}
            }
        },
        'errors': {
            'model_name': 'error_message'
        }
    }
    """
    logger.info(f"补测论文: {Path(paper_path).name}, 模型: {empty_models}")

    results = {}
    errors = {}

    try:
        # 预处理论文
        paper_content = process_file(paper_path)

        # 对每个空状态模型运行评审
        for model in empty_models:
            try:
                # 使用 run_convergence_test 运行单个模型的评审
                # 注意：run_convergence_test 是为多模型设计的，我们需要只传入一个模型
                result = await run_convergence_test(
                    framework_path=framework_path,
                    paper_path=paper_path,
                    model_names=[model],  # 只评审这一个模型
                    include_precheck=True
                )

                # 提取该模型的结果
                if result and 'precheck' in result and model in result['precheck']:
                    results[model] = {
                        'precheck': result['precheck'][model],
                        'dimensions': result.get('dimensions', {})
                    }
                    logger.info(f"  {model}: 补测成功")
                else:
                    errors[model] = "评审结果格式异常"
                    logger.warning(f"  {model}: 评审结果格式异常")

            except Exception as e:
                error_msg = str(e)
                errors[model] = error_msg
                logger.error(f"  {model}: 补测失败 - {error_msg}")

                # 检查是否是内容审查失败
                if 'data_inspection_failed' in error_msg or 'DataInspectionFailed' in error_msg:
                    logger.warning(f"  {model}: 内容审查失败，跳过")

        success = len(results) > 0

        return {
            'success': success,
            'results': results,
            'errors': errors
        }

    except Exception as e:
        logger.error(f"补测论文失败: {e}")
        return {
            'success': False,
            'results': {},
            'errors': {'all': str(e)}
        }


def merge_results(
    original_result: Dict,
    retest_result: Dict,
    empty_models: List[str]
) -> Dict:
    """
    合并补测结果到原始结果

    策略：
    - 用补测结果替换空状态模型的 precheck 和 dimensions
    - 保留其他模型的原始结果
    - 重新计算 overall 统计
    """
    merged = original_result.copy()

    # 合并 precheck
    if 'precheck' not in merged:
        merged['precheck'] = {}

    for model in empty_models:
        if model in retest_result.get('results', {}):
            model_result = retest_result['results'][model]
            merged['precheck'][model] = model_result.get('precheck', {})

    # 合并 dimensions
    if 'dimensions' not in merged:
        merged['dimensions'] = {}

    for model in empty_models:
        if model in retest_result.get('results', {}):
            model_result = retest_result['results'][model]
            model_dimensions = model_result.get('dimensions', {})

            # 合并每个维度的模型评分
            for dim_name, dim_data in model_dimensions.items():
                if dim_name not in merged['dimensions']:
                    merged['dimensions'][dim_name] = {}

                # 更新该模型在该维度的评分
                if 'model_scores' not in merged['dimensions'][dim_name]:
                    merged['dimensions'][dim_name]['model_scores'] = {}

                if model in dim_data.get('model_scores', {}):
                    merged['dimensions'][dim_name]['model_scores'][model] = dim_data['model_scores'][model]

                # 更新 raw_outputs
                if 'raw_outputs' not in merged['dimensions'][dim_name]:
                    merged['dimensions'][dim_name]['raw_outputs'] = {}

                if model in dim_data.get('raw_outputs', {}):
                    merged['dimensions'][dim_name]['raw_outputs'][model] = dim_data['raw_outputs'][model]

    # 重新计算统计（如果有多个模型的评分）
    for dim_name, dim_data in merged.get('dimensions', {}).items():
        model_scores = dim_data.get('model_scores', {})
        if model_scores:
            scores = [s for s in model_scores.values() if isinstance(s, (int, float))]
            if scores:
                import statistics
                dim_data['mean'] = statistics.mean(scores)
                if len(scores) > 1:
                    dim_data['std'] = statistics.stdev(scores)
                else:
                    dim_data['std'] = 0.0

    return merged


def generate_retest_report(
    tasks: List[Dict],
    retest_results: List[Dict],
    output_path: Path
):
    """生成补测报告"""
    # 统计
    total_papers = len(tasks)
    retested_papers = sum(1 for r in retest_results if r.get('success', False))
    failed_papers_count = total_papers - retested_papers
    success_rate = (retested_papers / total_papers * 100) if total_papers > 0 else 0

    # 模型统计
    model_stats = defaultdict(lambda: {'total': 0, 'success': 0, 'failed': 0, 'still_empty': 0})

    for task, result in zip(tasks, retest_results):
        empty_models = task['empty_models']

        for model in empty_models:
            model_stats[model]['total'] += 1

            if model in result.get('results', {}):
                model_stats[model]['success'] += 1
            elif model in result.get('errors', {}):
                model_stats[model]['failed'] += 1
            else:
                model_stats[model]['still_empty'] += 1

    # 失败论文列表
    failed_papers = []
    still_empty_papers = []

    for task, result in zip(tasks, retest_results):
        paper_id = task['paper_id']
        empty_models = task['empty_models']

        for model in empty_models:
            if model in result.get('errors', {}):
                failed_papers.append({
                    'paper_id': paper_id,
                    'model': model,
                    'error': result['errors'][model]
                })
            elif model not in result.get('results', {}):
                still_empty_papers.append({
                    'paper_id': paper_id,
                    'model': model
                })

    # 生成报告
    report = {
        'summary': {
            'total_papers': total_papers,
            'retested_papers': retested_papers,
            'failed_papers': failed_papers_count,
            'success_rate': round(success_rate, 2)
        },
        'model_stats': dict(model_stats),
        'failed_papers': failed_papers,
        'still_empty_papers': still_empty_papers,
        'timestamp': datetime.now().isoformat()
    }

    # 保存报告
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"补测报告已保存: {output_path}")

    return report


async def main():
    parser = argparse.ArgumentParser(description='补测 Phase 2 Round 1 空状态论文')
    parser.add_argument('--error-summary', required=True, help='错误汇总文件路径')
    parser.add_argument('--round1-dir', required=True, help='Round 1 结果目录')
    parser.add_argument('--framework', default='configs/frameworks/law-v2.55-cross-review.yaml', help='评审框架配置文件')
    parser.add_argument('--concurrency', type=int, default=3, help='并发数')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行，不实际调用 API')
    parser.add_argument('--base-dir', default='.', help='论文文件基础目录')

    args = parser.parse_args()

    # 路径处理
    error_summary_path = Path(args.error_summary)
    round1_dir = Path(args.round1_dir)
    framework_path = args.framework
    base_dir = Path(args.base_dir)
    output_dir = error_summary_path.parent

    # 配置日志
    global logger
    logger = setup_logging(output_dir)

    logger.info("=" * 80)
    logger.info("开始补测 Phase 2 Round 1 空状态论文")
    logger.info("=" * 80)
    logger.info(f"错误汇总: {error_summary_path}")
    logger.info(f"Round 1 目录: {round1_dir}")
    logger.info(f"评审框架: {framework_path}")
    logger.info(f"并发数: {args.concurrency}")
    logger.info(f"模拟运行: {args.dry_run}")
    logger.info("")

    # 步骤 1：加载空状态论文清单
    logger.info("步骤 1：加载空状态论文清单")
    empty_status_papers = load_empty_status_papers(error_summary_path)
    logger.info("")

    # 步骤 2：构建补测任务列表
    logger.info("步骤 2：构建补测任务列表")
    tasks = build_retest_tasks(empty_status_papers, round1_dir, base_dir)
    logger.info("")

    if not tasks:
        logger.warning("没有需要补测的论文")
        return

    # 步骤 3：执行补测
    logger.info("步骤 3：执行补测")
    logger.info(f"总任务数: {len(tasks)}")
    logger.info("")

    retest_results = []

    for i, task in enumerate(tasks, 1):
        paper_id = task['paper_id']
        paper_path = task['paper_path']
        empty_models = task['empty_models']
        original_result_path = task['original_result_path']

        logger.info(f"[{i}/{len(tasks)}] 处理 {paper_id}")

        # 加载原始结果
        with open(original_result_path, 'r', encoding='utf-8') as f:
            original_result = json.load(f)

        # 检查是否已补测
        if is_already_retested(original_result, empty_models):
            logger.info(f"  {paper_id}: 已补测，跳过")
            retest_results.append({'success': True, 'results': {}, 'errors': {}})
            continue

        if args.dry_run:
            logger.info(f"  {paper_id}: 模拟运行，跳过实际补测")
            retest_results.append({'success': True, 'results': {}, 'errors': {}})
            continue

        # 执行补测
        retest_result = await retest_paper_models(
            paper_path=paper_path,
            empty_models=empty_models,
            framework_path=framework_path,
            logger=logger
        )

        retest_results.append(retest_result)

        # 合并结果
        if retest_result['success']:
            merged_result = merge_results(original_result, retest_result, empty_models)

            # 保存更新后的结果
            with open(original_result_path, 'w', encoding='utf-8') as f:
                json.dump(merged_result, f, ensure_ascii=False, indent=2)

            logger.info(f"  {paper_id}: 补测成功，结果已更新")
        else:
            logger.warning(f"  {paper_id}: 补测失败")

        logger.info("")

        # 控制并发（简单的延迟）
        if i < len(tasks):
            await asyncio.sleep(1)

    # 步骤 4：生成补测报告
    logger.info("步骤 4：生成补测报告")
    report_path = output_dir / "retest-report.json"
    report = generate_retest_report(tasks, retest_results, report_path)
    logger.info("")

    # 输出汇总
    logger.info("=" * 80)
    logger.info("补测完成")
    logger.info("=" * 80)
    logger.info(f"总论文数: {report['summary']['total_papers']}")
    logger.info(f"补测成功: {report['summary']['retested_papers']}")
    logger.info(f"补测失败: {report['summary']['failed_papers']}")
    logger.info(f"成功率: {report['summary']['success_rate']}%")
    logger.info("")
    logger.info("模型统计:")
    for model, stats in report['model_stats'].items():
        logger.info(f"  {model}:")
        logger.info(f"    总数: {stats['total']}")
        logger.info(f"    成功: {stats['success']}")
        logger.info(f"    失败: {stats['failed']}")
        logger.info(f"    仍为空: {stats['still_empty']}")
    logger.info("")
    logger.info(f"补测报告: {report_path}")
    logger.info(f"执行日志: {output_dir / 'retest-execution.log'}")


if __name__ == '__main__':
    asyncio.run(main())
