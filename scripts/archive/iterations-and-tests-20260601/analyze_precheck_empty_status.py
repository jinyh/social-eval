#!/usr/bin/env python3
"""
分析预检阶段返回空状态的论文

检查：
1. 哪些论文的哪些模型返回了空状态
2. 空状态是否影响了预检结论（是否有其他模型通过）
3. 是否需要补测
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

def load_result(file_path: Path) -> Dict[str, Any]:
    """加载单个评审结果文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_empty_status(results_dir: Path):
    """分析空状态情况"""
    empty_status_papers = []

    result_files = sorted(results_dir.glob('paper-*.json'))

    for file_path in result_files:
        paper_id = file_path.stem
        result = load_result(file_path)
        paper_name = result.get('paper', 'unknown')
        precheck = result.get('precheck', {})

        empty_models = []
        other_models_status = {}

        for model, data in precheck.items():
            if isinstance(data, dict):
                status = data.get('status', '')
                conclusion = data.get('conclusion', '')

                # 检查是否为空状态
                if status == '' and conclusion == '':
                    empty_models.append(model)
                else:
                    other_models_status[model] = {
                        'status': status,
                        'conclusion': conclusion
                    }

        if empty_models:
            # 分析其他模型的结论
            other_conclusions = [s['conclusion'] for s in other_models_status.values()]
            pass_count = sum(1 for c in other_conclusions if c == 'enter_six_dimension_review')
            reject_count = sum(1 for c in other_conclusions if c == 'obviously_ineligible')
            boundary_count = sum(1 for c in other_conclusions if c == 'boundary_review')

            empty_status_papers.append({
                'paper_id': paper_id,
                'paper_name': paper_name,
                'empty_models': empty_models,
                'other_models_status': other_models_status,
                'pass_count': pass_count,
                'reject_count': reject_count,
                'boundary_count': boundary_count,
                'total_valid_models': len(other_models_status)
            })

    return empty_status_papers

def print_report(empty_status_papers: List[Dict[str, Any]]):
    """打印分析报告"""
    print("=" * 80)
    print("预检阶段空状态分析")
    print("=" * 80)
    print()

    print(f"空状态论文总数: {len(empty_status_papers)}")
    print()

    # 按影响程度分类
    need_retest = []  # 需要补测：其他模型有通过的
    no_need_retest = []  # 不需要补测：其他模型全部拒绝

    for paper in empty_status_papers:
        if paper['pass_count'] > 0 or paper['boundary_count'] > 0:
            need_retest.append(paper)
        elif paper['reject_count'] == paper['total_valid_models']:
            no_need_retest.append(paper)
        else:
            need_retest.append(paper)  # 保守起见，其他情况也补测

    print(f"需要补测: {len(need_retest)} 篇（其他模型有通过或边界判断）")
    print(f"无需补测: {len(no_need_retest)} 篇（其他模型全部拒绝）")
    print()

    # 需要补测的详情
    if need_retest:
        print("-" * 80)
        print(f"需要补测的论文 ({len(need_retest)} 篇)")
        print("-" * 80)
        for paper in need_retest:
            print(f"\n{paper['paper_id']}: {paper['paper_name']}")
            print(f"  空状态模型: {', '.join(paper['empty_models'])}")
            print(f"  其他模型: 通过={paper['pass_count']}, 拒绝={paper['reject_count']}, 边界={paper['boundary_count']}")
            for model, status in paper['other_models_status'].items():
                print(f"    {model}: {status['conclusion']} (status={status['status']})")

    # 无需补测的详情
    if no_need_retest:
        print()
        print("-" * 80)
        print(f"无需补测的论文 ({len(no_need_retest)} 篇)")
        print("-" * 80)
        for paper in no_need_retest:
            print(f"\n{paper['paper_id']}: {paper['paper_name']}")
            print(f"  空状态模型: {', '.join(paper['empty_models'])}")
            print(f"  其他模型全部拒绝 (reject_count={paper['reject_count']})")

    print()
    print("=" * 80)
    print("结论:")
    print("=" * 80)
    if need_retest:
        print(f"建议补测 {len(need_retest)} 篇论文的空状态模型")
        print("原因: 其他模型有通过或边界判断，空状态可能影响最终预检结论")
    else:
        print("无需补测")

    if no_need_retest:
        print(f"\n{len(no_need_retest)} 篇论文无需补测")
        print("原因: 其他模型全部拒绝，空状态不影响最终预检结论")

    return need_retest, no_need_retest

def main():
    results_dir = Path(__file__).parent.parent / 'results' / 'phase2-evaluation' / 'round1'

    if not results_dir.exists():
        print(f"错误: 结果目录不存在: {results_dir}")
        return

    empty_status_papers = analyze_empty_status(results_dir)
    need_retest, no_need_retest = print_report(empty_status_papers)

    # 保存补测清单
    if need_retest:
        retest_file = results_dir / 'precheck_empty_status_retest.json'
        with open(retest_file, 'w', encoding='utf-8') as f:
            json.dump({
                'need_retest': need_retest,
                'no_need_retest': no_need_retest,
                'summary': {
                    'total_empty_status': len(empty_status_papers),
                    'need_retest_count': len(need_retest),
                    'no_need_retest_count': len(no_need_retest)
                }
            }, f, ensure_ascii=False, indent=2)
        print(f"\n补测清单已保存至: {retest_file}")

if __name__ == '__main__':
    main()
