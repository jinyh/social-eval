#!/usr/bin/env python3
"""
分析预检失败中非空状态的论文

检查：
1. 这 55 篇论文的失败原因
2. 是否需要补测
3. 是否需要人工复核
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

def load_result(file_path: Path) -> Dict[str, Any]:
    """加载单个评审结果文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_non_empty_failures(results_dir: Path):
    """分析非空状态的预检失败"""
    result_files = sorted(results_dir.glob('paper-*.json'))

    non_empty_failures = []

    for file_path in result_files:
        paper_id = file_path.stem
        result = load_result(file_path)
        paper_name = result.get('paper', 'unknown')
        precheck = result.get('precheck', {})

        # 检查是否有空状态
        has_empty = False
        for model, data in precheck.items():
            if isinstance(data, dict):
                status = data.get('status', '')
                conclusion = data.get('conclusion', '')
                if status == '' and conclusion == '':
                    has_empty = True
                    break

        # 如果没有空状态，检查是否有失败
        if not has_empty:
            failure_info = {
                'paper_id': paper_id,
                'paper_name': paper_name,
                'model_conclusions': {},
                'reject_count': 0,
                'pass_count': 0,
                'boundary_count': 0,
                'manual_review_count': 0
            }

            for model, data in precheck.items():
                if isinstance(data, dict):
                    conclusion = data.get('conclusion', '')
                    status = data.get('status', '')
                    requires_manual = data.get('requires_manual_confirmation', False)

                    failure_info['model_conclusions'][model] = {
                        'conclusion': conclusion,
                        'status': status,
                        'requires_manual': requires_manual
                    }

                    if conclusion == 'obviously_ineligible':
                        failure_info['reject_count'] += 1
                    elif conclusion == 'enter_six_dimension_review':
                        failure_info['pass_count'] += 1
                    elif conclusion == 'boundary_review':
                        failure_info['boundary_count'] += 1

                    if requires_manual:
                        failure_info['manual_review_count'] += 1

            # 判断是否为失败（至少有一个模型拒绝或需要人工确认）
            if failure_info['reject_count'] > 0 or failure_info['manual_review_count'] > 0:
                non_empty_failures.append(failure_info)

    return non_empty_failures

def print_report(non_empty_failures: List[Dict[str, Any]]):
    """打印分析报告"""
    print("=" * 80)
    print("预检失败（非空状态）分析")
    print("=" * 80)
    print()

    print(f"非空状态失败论文总数: {len(non_empty_failures)}")
    print()

    # 按失败类型分类
    all_reject = []  # 所有模型都拒绝
    majority_reject = []  # 多数模型拒绝
    boundary_only = []  # 仅边界判断
    mixed = []  # 混合情况

    for paper in non_empty_failures:
        total_models = len(paper['model_conclusions'])

        if paper['reject_count'] == total_models:
            all_reject.append(paper)
        elif paper['reject_count'] >= total_models / 2:
            majority_reject.append(paper)
        elif paper['boundary_count'] > 0 and paper['reject_count'] == 0:
            boundary_only.append(paper)
        else:
            mixed.append(paper)

    print(f"所有模型拒绝: {len(all_reject)} 篇（无需补测）")
    print(f"多数模型拒绝: {len(majority_reject)} 篇（建议人工复核）")
    print(f"仅边界判断: {len(boundary_only)} 篇（需要人工确认）")
    print(f"混合情况: {len(mixed)} 篇（需要人工复核）")
    print()

    # 所有模型拒绝的详情
    if all_reject:
        print("-" * 80)
        print(f"所有模型拒绝 ({len(all_reject)} 篇) - 无需补测")
        print("-" * 80)
        for paper in all_reject[:10]:  # 只显示前 10 篇
            print(f"\n{paper['paper_id']}: {paper['paper_name']}")
            for model, info in paper['model_conclusions'].items():
                print(f"  {model}: {info['conclusion']}")
        if len(all_reject) > 10:
            print(f"\n... 还有 {len(all_reject) - 10} 篇")

    # 多数模型拒绝的详情
    if majority_reject:
        print()
        print("-" * 80)
        print(f"多数模型拒绝 ({len(majority_reject)} 篇) - 建议人工复核")
        print("-" * 80)
        for paper in majority_reject:
            print(f"\n{paper['paper_id']}: {paper['paper_name']}")
            print(f"  通过={paper['pass_count']}, 拒绝={paper['reject_count']}, 边界={paper['boundary_count']}")
            for model, info in paper['model_conclusions'].items():
                print(f"    {model}: {info['conclusion']}")

    # 仅边界判断的详情
    if boundary_only:
        print()
        print("-" * 80)
        print(f"仅边界判断 ({len(boundary_only)} 篇) - 需要人工确认")
        print("-" * 80)
        for paper in boundary_only:
            print(f"\n{paper['paper_id']}: {paper['paper_name']}")
            print(f"  通过={paper['pass_count']}, 边界={paper['boundary_count']}")
            for model, info in paper['model_conclusions'].items():
                print(f"    {model}: {info['conclusion']}")

    # 混合情况的详情
    if mixed:
        print()
        print("-" * 80)
        print(f"混合情况 ({len(mixed)} 篇) - 需要人工复核")
        print("-" * 80)
        for paper in mixed:
            print(f"\n{paper['paper_id']}: {paper['paper_name']}")
            print(f"  通过={paper['pass_count']}, 拒绝={paper['reject_count']}, 边界={paper['boundary_count']}")
            for model, info in paper['model_conclusions'].items():
                print(f"    {model}: {info['conclusion']}")

    print()
    print("=" * 80)
    print("结论:")
    print("=" * 80)
    print(f"无需补测: {len(all_reject)} 篇（所有模型一致拒绝）")
    print(f"需要人工复核: {len(majority_reject) + len(boundary_only) + len(mixed)} 篇")
    print("  - 多数模型拒绝但有分歧")
    print("  - 边界论文需要人工判断")
    print("  - 模型意见混合")

    return {
        'all_reject': all_reject,
        'majority_reject': majority_reject,
        'boundary_only': boundary_only,
        'mixed': mixed
    }

def main():
    results_dir = Path(__file__).parent.parent / 'results' / 'phase2-evaluation' / 'round1'

    if not results_dir.exists():
        print(f"错误: 结果目录不存在: {results_dir}")
        return

    non_empty_failures = analyze_non_empty_failures(results_dir)
    categorized = print_report(non_empty_failures)

    # 保存分析结果
    report_file = results_dir / 'precheck_non_empty_failures.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(non_empty_failures),
            'all_reject': categorized['all_reject'],
            'majority_reject': categorized['majority_reject'],
            'boundary_only': categorized['boundary_only'],
            'mixed': categorized['mixed'],
            'summary': {
                'all_reject_count': len(categorized['all_reject']),
                'majority_reject_count': len(categorized['majority_reject']),
                'boundary_only_count': len(categorized['boundary_only']),
                'mixed_count': len(categorized['mixed'])
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"\n详细报告已保存至: {report_file}")

if __name__ == '__main__':
    main()
