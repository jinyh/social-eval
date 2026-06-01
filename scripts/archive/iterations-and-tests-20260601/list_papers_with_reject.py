#!/usr/bin/env python3
"""
列出至少有 1 个模型拒绝的所有论文
"""

import json
from pathlib import Path
from typing import Dict, List, Any

def load_result(file_path: Path) -> Dict[str, Any]:
    """加载单个评审结果文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def find_papers_with_reject(results_dir: Path):
    """查找至少有 1 个模型拒绝的论文"""
    result_files = sorted(results_dir.glob('paper-*.json'))

    papers_with_reject = []

    for file_path in result_files:
        paper_id = file_path.stem
        result = load_result(file_path)
        paper_name = result.get('paper', 'unknown')
        precheck = result.get('precheck', {})

        # 统计各模型的结论
        reject_models = []
        pass_models = []
        boundary_models = []
        empty_models = []

        for model, data in precheck.items():
            if isinstance(data, dict):
                conclusion = data.get('conclusion', '')
                status = data.get('status', '')

                if conclusion == 'obviously_ineligible':
                    reject_models.append(model)
                elif conclusion == 'enter_six_dimension_review':
                    pass_models.append(model)
                elif conclusion == 'boundary_review':
                    boundary_models.append(model)
                elif conclusion == '' and status == '':
                    empty_models.append(model)

        # 如果有至少 1 个模型拒绝
        if reject_models:
            papers_with_reject.append({
                'paper_id': paper_id,
                'paper_name': paper_name,
                'reject_count': len(reject_models),
                'reject_models': reject_models,
                'pass_count': len(pass_models),
                'pass_models': pass_models,
                'boundary_count': len(boundary_models),
                'boundary_models': boundary_models,
                'empty_count': len(empty_models),
                'empty_models': empty_models
            })

    return papers_with_reject

def print_report(papers_with_reject: List[Dict[str, Any]]):
    """打印报告"""
    print("=" * 80)
    print("至少有 1 个模型拒绝（obviously_ineligible）的论文")
    print("=" * 80)
    print()
    print(f"总数: {len(papers_with_reject)} 篇")
    print()

    # 按拒绝数量分组
    by_reject_count = {4: [], 3: [], 2: [], 1: []}
    for paper in papers_with_reject:
        by_reject_count[paper['reject_count']].append(paper)

    for reject_count in [4, 3, 2, 1]:
        papers = by_reject_count[reject_count]
        if papers:
            print("-" * 80)
            print(f"{reject_count} 个模型拒绝 ({len(papers)} 篇)")
            print("-" * 80)
            for i, paper in enumerate(papers, 1):
                # 提取论文标题
                title = paper['paper_name'].split('/')[-1].replace('.pdf', '')
                print(f"\n{i}. {paper['paper_id']}: {title}")
                print(f"   拒绝: {', '.join(paper['reject_models'])}")
                if paper['pass_models']:
                    print(f"   通过: {', '.join(paper['pass_models'])}")
                if paper['boundary_models']:
                    print(f"   边界: {', '.join(paper['boundary_models'])}")
                if paper['empty_models']:
                    print(f"   空状态: {', '.join(paper['empty_models'])}")
            print()

def main():
    results_dir = Path(__file__).parent.parent / 'results' / 'phase2-evaluation' / 'round1'

    if not results_dir.exists():
        print(f"错误: 结果目录不存在: {results_dir}")
        return

    papers_with_reject = find_papers_with_reject(results_dir)
    print_report(papers_with_reject)

    # 保存结果
    output_file = results_dir / 'papers_with_any_reject.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(papers_with_reject),
            'papers': papers_with_reject
        }, f, ensure_ascii=False, indent=2)
    print(f"详细结果已保存至: {output_file}")

if __name__ == '__main__':
    main()
