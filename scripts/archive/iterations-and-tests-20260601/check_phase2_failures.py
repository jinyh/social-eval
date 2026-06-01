#!/usr/bin/env python3
"""
检查 Phase 2 Round 1 评审结果中的失败情况

分析维度：
1. 预检失败（未进入六维评分）
2. 维度评分失败（API 错误、超时等）
3. 内容审查问题
4. 其他异常情况
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

def load_result(file_path: Path) -> Dict[str, Any]:
    """加载单个评审结果文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def check_precheck_failures(result: Dict[str, Any]) -> List[str]:
    """检查预检阶段的失败"""
    failures = []
    precheck = result.get('precheck', {})

    for model, data in precheck.items():
        if isinstance(data, dict):
            status = data.get('status', '')
            conclusion = data.get('conclusion', '')

            # 检查是否未通过预检
            if conclusion != 'enter_six_dimension_review':
                failures.append(f"{model}: {conclusion} (status={status})")

            # 检查是否有错误标记
            if data.get('requires_manual_confirmation', False):
                failures.append(f"{model}: 需要人工确认")

    return failures

def check_dimension_failures(result: Dict[str, Any]) -> Dict[str, List[str]]:
    """检查六维评分阶段的失败"""
    failures = defaultdict(list)
    dimensions = result.get('dimensions', {})

    for dim_name, dim_data in dimensions.items():
        # 检查是否有错误记录
        errors = dim_data.get('errors', {})
        if errors:
            for model, error in errors.items():
                failures[dim_name].append(f"{model}: {error}")

        # 检查是否有模型缺失评分
        raw_outputs = dim_data.get('raw_outputs', {})
        expected_models = result.get('models', [])
        for model in expected_models:
            if model not in raw_outputs:
                failures[dim_name].append(f"{model}: 缺失评分")

    return dict(failures)

def check_content_inspection_issues(result: Dict[str, Any]) -> List[str]:
    """检查内容审查问题"""
    issues = []

    # 检查预检阶段
    precheck = result.get('precheck', {})
    for model, data in precheck.items():
        if isinstance(data, dict):
            if 'data_inspection_failed' in str(data):
                issues.append(f"预检-{model}: 内容审查失败")

    # 检查维度评分阶段
    dimensions = result.get('dimensions', {})
    for dim_name, dim_data in dimensions.items():
        errors = dim_data.get('errors', {})
        for model, error in errors.items():
            if 'data_inspection_failed' in str(error) or 'DataInspectionDeny' in str(error):
                issues.append(f"{dim_name}-{model}: 内容审查失败")

    return issues

def analyze_results(results_dir: Path) -> Dict[str, Any]:
    """分析所有评审结果"""
    stats = {
        'total': 0,
        'precheck_failures': [],
        'dimension_failures': [],
        'content_inspection_issues': [],
        'complete_success': [],
        'partial_failure': []
    }

    result_files = sorted(results_dir.glob('paper-*.json'))
    stats['total'] = len(result_files)

    for file_path in result_files:
        paper_id = file_path.stem
        result = load_result(file_path)
        paper_name = result.get('paper', 'unknown')

        # 检查各类失败
        precheck_fails = check_precheck_failures(result)
        dimension_fails = check_dimension_failures(result)
        content_issues = check_content_inspection_issues(result)

        has_failure = bool(precheck_fails or dimension_fails or content_issues)

        if has_failure:
            failure_info = {
                'paper_id': paper_id,
                'paper_name': paper_name,
                'precheck_failures': precheck_fails,
                'dimension_failures': dimension_fails,
                'content_inspection_issues': content_issues
            }

            if precheck_fails:
                stats['precheck_failures'].append(failure_info)
            elif dimension_fails or content_issues:
                stats['partial_failure'].append(failure_info)
        else:
            stats['complete_success'].append({
                'paper_id': paper_id,
                'paper_name': paper_name
            })

    return stats

def print_report(stats: Dict[str, Any]):
    """打印分析报告"""
    print("=" * 80)
    print("Phase 2 Round 1 评审失败情况分析")
    print("=" * 80)
    print()

    print(f"总论文数: {stats['total']}")
    print(f"完全成功: {len(stats['complete_success'])} ({len(stats['complete_success'])/stats['total']*100:.1f}%)")
    print(f"预检失败: {len(stats['precheck_failures'])} ({len(stats['precheck_failures'])/stats['total']*100:.1f}%)")
    print(f"部分失败: {len(stats['partial_failure'])} ({len(stats['partial_failure'])/stats['total']*100:.1f}%)")
    print()

    # 预检失败详情
    if stats['precheck_failures']:
        print("-" * 80)
        print(f"预检失败详情 ({len(stats['precheck_failures'])} 篇)")
        print("-" * 80)
        for item in stats['precheck_failures']:
            print(f"\n{item['paper_id']}: {item['paper_name']}")
            for failure in item['precheck_failures']:
                print(f"  - {failure}")
            if item['content_inspection_issues']:
                print("  内容审查问题:")
                for issue in item['content_inspection_issues']:
                    print(f"    - {issue}")

    # 部分失败详情
    if stats['partial_failure']:
        print()
        print("-" * 80)
        print(f"部分失败详情 ({len(stats['partial_failure'])} 篇)")
        print("-" * 80)
        for item in stats['partial_failure']:
            print(f"\n{item['paper_id']}: {item['paper_name']}")

            if item['dimension_failures']:
                print("  维度评分失败:")
                for dim, failures in item['dimension_failures'].items():
                    print(f"    {dim}:")
                    for failure in failures:
                        print(f"      - {failure}")

            if item['content_inspection_issues']:
                print("  内容审查问题:")
                for issue in item['content_inspection_issues']:
                    print(f"    - {issue}")

    # 统计内容审查问题
    all_content_issues = []
    for item in stats['precheck_failures'] + stats['partial_failure']:
        all_content_issues.extend(item['content_inspection_issues'])

    if all_content_issues:
        print()
        print("-" * 80)
        print(f"内容审查问题汇总 ({len(all_content_issues)} 个)")
        print("-" * 80)
        for issue in all_content_issues:
            print(f"  - {issue}")

    print()
    print("=" * 80)

def main():
    results_dir = Path(__file__).parent.parent / 'results' / 'phase2-evaluation' / 'round1'

    if not results_dir.exists():
        print(f"错误: 结果目录不存在: {results_dir}")
        return

    stats = analyze_results(results_dir)
    print_report(stats)

    # 保存详细报告
    report_file = results_dir / 'failure_analysis.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"\n详细报告已保存至: {report_file}")

if __name__ == '__main__':
    main()
