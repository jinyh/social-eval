#!/usr/bin/env python3
"""
查找所有 4 个模型一致拒绝的论文（包括空状态和非空状态）
"""

import json
from pathlib import Path
from typing import Dict, List, Any

def load_result(file_path: Path) -> Dict[str, Any]:
    """加载单个评审结果文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def find_all_reject_papers(results_dir: Path):
    """查找所有 4 个模型一致拒绝的论文"""
    result_files = sorted(results_dir.glob('paper-*.json'))

    all_reject_papers = []

    for file_path in result_files:
        paper_id = file_path.stem
        result = load_result(file_path)
        paper_name = result.get('paper', 'unknown')
        precheck = result.get('precheck', {})

        # 统计各模型的结论
        conclusions = {}
        for model, data in precheck.items():
            if isinstance(data, dict):
                conclusion = data.get('conclusion', '')
                conclusions[model] = conclusion

        # 检查是否所有模型都拒绝
        if len(conclusions) == 4:  # 确保有 4 个模型的结果
            if all(c == 'obviously_ineligible' for c in conclusions.values()):
                all_reject_papers.append({
                    'paper_id': paper_id,
                    'paper_name': paper_name,
                    'conclusions': conclusions
                })

    return all_reject_papers

def print_report(all_reject_papers: List[Dict[str, Any]]):
    """打印报告"""
    print("=" * 80)
    print("所有模型一致拒绝的论文（obviously_ineligible）")
    print("=" * 80)
    print()
    print(f"总数: {len(all_reject_papers)} 篇")
    print()

    for i, paper in enumerate(all_reject_papers, 1):
        print(f"{i}. {paper['paper_id']}")
        # 提取论文标题（去掉路径前缀）
        title = paper['paper_name'].split('/')[-1].replace('.pdf', '')
        print(f"   {title}")
        print()

def main():
    results_dir = Path(__file__).parent.parent / 'results' / 'phase2-evaluation' / 'round1'

    if not results_dir.exists():
        print(f"错误: 结果目录不存在: {results_dir}")
        return

    all_reject_papers = find_all_reject_papers(results_dir)
    print_report(all_reject_papers)

    # 保存结果
    output_file = results_dir / 'all_models_reject.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(all_reject_papers),
            'papers': all_reject_papers
        }, f, ensure_ascii=False, indent=2)
    print(f"详细结果已保存至: {output_file}")

if __name__ == '__main__':
    main()
