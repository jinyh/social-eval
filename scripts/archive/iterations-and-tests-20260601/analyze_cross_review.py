#!/usr/bin/env python3
"""交叉评审结果分析脚本

对比第一轮和第二轮的评分变化，生成统计报告。

用法：
    python scripts/analyze_cross_review.py \
        --round1-dir results/phase1-100-papers-strictest \
        --round2-dir results/phase1-100-papers-cross-review \
        --output results/cross-review-analysis.json
"""

import argparse
import json
import statistics
from pathlib import Path
from collections import defaultdict
from typing import Dict, List


def load_results(result_dir: Path) -> List[Dict]:
    """加载指定目录下的所有评价结果"""
    results = []
    for json_file in sorted(result_dir.glob("paper-*.json")):
        with open(json_file, 'r', encoding='utf-8') as f:
            results.append(json.load(f))
    return results


def analyze_cross_review(round1_dir: Path, round2_dir: Path) -> Dict:
    """分析交叉评审结果"""

    # 加载结果
    round2_results = load_results(round2_dir)

    # 初始化统计
    stats = {
        'total_papers': len(round2_results),
        'dimensions': {},
        'models': {},
        'groups': {
            'a_group': {'models': ['glm-5.1', 'qwen3.6-plus'], 'changes': []},
            'b_group': {'models': ['deepseek-v4-pro', 'kimi-k2.6'], 'changes': []}
        },
        'overall': {
            'round1_mean': [],
            'round2_mean': [],
            'convergence_improvements': []
        }
    }

    # 按维度统计
    dimension_stats = defaultdict(lambda: {
        'round1_scores': [],
        'round2_scores': [],
        'changes': [],
        'score_increased': 0,
        'score_decreased': 0,
        'score_unchanged': 0,
        'convergence_improvements': []
    })

    # 按模型统计
    model_stats = defaultdict(lambda: {
        'round1_scores': [],
        'round2_scores': [],
        'changes': [],
        'score_increased': 0,
        'score_decreased': 0,
        'score_unchanged': 0,
        'accepted_points_count': 0,
        'rejected_points_count': 0
    })

    # 遍历所有论文
    for result in round2_results:
        dimensions = result.get('dimensions', {})

        for dim_key, dim_data in dimensions.items():
            dim_name = dim_data.get('name_zh', dim_key)

            # 维度级统计
            round1_mean = dim_data.get('round1_mean', 0)
            round2_mean = dim_data.get('round2_mean', 0)
            convergence_improvement = dim_data.get('convergence_improvement', 0)

            dimension_stats[dim_name]['round1_scores'].append(round1_mean)
            dimension_stats[dim_name]['round2_scores'].append(round2_mean)
            dimension_stats[dim_name]['changes'].append(round2_mean - round1_mean)
            dimension_stats[dim_name]['convergence_improvements'].append(convergence_improvement)

            # 模型级统计
            changes = dim_data.get('changes', {})
            raw_outputs = dim_data.get('raw_outputs', {})

            for model_name, change_info in changes.items():
                original = change_info.get('original')
                revised = change_info.get('revised')

                if original is not None and revised is not None:
                    model_stats[model_name]['round1_scores'].append(original)
                    model_stats[model_name]['round2_scores'].append(revised)

                    diff = revised - original
                    model_stats[model_name]['changes'].append(diff)

                    if diff > 0:
                        model_stats[model_name]['score_increased'] += 1
                        dimension_stats[dim_name]['score_increased'] += 1
                    elif diff < 0:
                        model_stats[model_name]['score_decreased'] += 1
                        dimension_stats[dim_name]['score_decreased'] += 1
                    else:
                        model_stats[model_name]['score_unchanged'] += 1
                        dimension_stats[dim_name]['score_unchanged'] += 1

                    # 统计接受/拒绝观点
                    if model_name in raw_outputs:
                        accepted = raw_outputs[model_name].get('accepted_points', [])
                        rejected = raw_outputs[model_name].get('rejected_points', [])
                        model_stats[model_name]['accepted_points_count'] += len(accepted)
                        model_stats[model_name]['rejected_points_count'] += len(rejected)

                    # 分组统计
                    if model_name in stats['groups']['a_group']['models']:
                        stats['groups']['a_group']['changes'].append(diff)
                    elif model_name in stats['groups']['b_group']['models']:
                        stats['groups']['b_group']['changes'].append(diff)

        # 总体统计
        overall = result.get('overall', {})
        stats['overall']['round1_mean'].append(overall.get('round1_final_score_mean', 0))
        stats['overall']['round2_mean'].append(overall.get('round2_final_score_mean', 0))

    # 计算维度汇总统计
    for dim_name, dim_stat in dimension_stats.items():
        stats['dimensions'][dim_name] = {
            'round1_mean': round(statistics.mean(dim_stat['round1_scores']), 2),
            'round2_mean': round(statistics.mean(dim_stat['round2_scores']), 2),
            'avg_change': round(statistics.mean(dim_stat['changes']), 2),
            'std_change': round(statistics.stdev(dim_stat['changes']), 2) if len(dim_stat['changes']) > 1 else 0,
            'score_increased': dim_stat['score_increased'],
            'score_decreased': dim_stat['score_decreased'],
            'score_unchanged': dim_stat['score_unchanged'],
            'avg_convergence_improvement': round(statistics.mean(dim_stat['convergence_improvements']), 2)
        }

    # 计算模型汇总统计
    for model_name, model_stat in model_stats.items():
        stats['models'][model_name] = {
            'round1_mean': round(statistics.mean(model_stat['round1_scores']), 2),
            'round2_mean': round(statistics.mean(model_stat['round2_scores']), 2),
            'avg_change': round(statistics.mean(model_stat['changes']), 2),
            'std_change': round(statistics.stdev(model_stat['changes']), 2) if len(model_stat['changes']) > 1 else 0,
            'score_increased': model_stat['score_increased'],
            'score_decreased': model_stat['score_decreased'],
            'score_unchanged': model_stat['score_unchanged'],
            'change_rate': round(
                (model_stat['score_increased'] + model_stat['score_decreased']) /
                len(model_stat['changes']) * 100, 1
            ) if model_stat['changes'] else 0,
            'avg_accepted_points': round(
                model_stat['accepted_points_count'] / len(model_stat['round1_scores']), 1
            ) if model_stat['round1_scores'] else 0,
            'avg_rejected_points': round(
                model_stat['rejected_points_count'] / len(model_stat['round1_scores']), 1
            ) if model_stat['round1_scores'] else 0
        }

    # 计算分组统计
    for group_name, group_data in stats['groups'].items():
        if group_data['changes']:
            group_data['avg_change'] = round(statistics.mean(group_data['changes']), 2)
            group_data['std_change'] = round(statistics.stdev(group_data['changes']), 2) if len(group_data['changes']) > 1 else 0
            group_data['total_changes'] = len(group_data['changes'])
        else:
            group_data['avg_change'] = 0
            group_data['std_change'] = 0
            group_data['total_changes'] = 0

    # 计算总体统计
    if stats['overall']['round1_mean']:
        stats['overall']['avg_round1_mean'] = round(statistics.mean(stats['overall']['round1_mean']), 2)
        stats['overall']['avg_round2_mean'] = round(statistics.mean(stats['overall']['round2_mean']), 2)
        stats['overall']['overall_change'] = round(
            stats['overall']['avg_round2_mean'] - stats['overall']['avg_round1_mean'], 2
        )

    return stats


def print_summary(stats: Dict):
    """打印统计摘要"""
    print("\n" + "=" * 80)
    print("交叉评审结果分析")
    print("=" * 80)

    print(f"\n总论文数：{stats['total_papers']}")

    # 总体变化
    print("\n【总体变化】")
    overall = stats['overall']
    print(f"第一轮平均分：{overall['avg_round1_mean']:.2f}")
    print(f"第二轮平均分：{overall['avg_round2_mean']:.2f}")
    print(f"总体变化：{overall['overall_change']:+.2f}")

    # 分组变化
    print("\n【分组变化】")
    for group_name, group_data in stats['groups'].items():
        print(f"\n{group_name.upper()}（{', '.join(group_data['models'])}）：")
        print(f"  平均变化：{group_data['avg_change']:+.2f} ± {group_data['std_change']:.2f}")
        print(f"  总变化次数：{group_data['total_changes']}")

    # 各维度变化
    print("\n【各维度变化】")
    for dim_name, dim_stat in stats['dimensions'].items():
        print(f"\n{dim_name}：")
        print(f"  第一轮：{dim_stat['round1_mean']:.2f} → 第二轮：{dim_stat['round2_mean']:.2f}")
        print(f"  平均变化：{dim_stat['avg_change']:+.2f} ± {dim_stat['std_change']:.2f}")
        print(f"  上调/下调/不变：{dim_stat['score_increased']}/{dim_stat['score_decreased']}/{dim_stat['score_unchanged']}")
        print(f"  收敛性改善：{dim_stat['avg_convergence_improvement']:+.2f}")

    # 各模型变化
    print("\n【各模型变化】")
    for model_name, model_stat in stats['models'].items():
        print(f"\n{model_name}：")
        print(f"  第一轮：{model_stat['round1_mean']:.2f} → 第二轮：{model_stat['round2_mean']:.2f}")
        print(f"  平均变化：{model_stat['avg_change']:+.2f} ± {model_stat['std_change']:.2f}")
        print(f"  上调/下调/不变：{model_stat['score_increased']}/{model_stat['score_decreased']}/{model_stat['score_unchanged']}")
        print(f"  修改率：{model_stat['change_rate']:.1f}%")
        print(f"  平均接受观点数：{model_stat['avg_accepted_points']:.1f}")
        print(f"  平均拒绝观点数：{model_stat['avg_rejected_points']:.1f}")


def main():
    parser = argparse.ArgumentParser(description='交叉评审结果分析')
    parser.add_argument('--round1-dir', required=True, help='第一轮结果目录')
    parser.add_argument('--round2-dir', required=True, help='第二轮结果目录')
    parser.add_argument('--output', required=True, help='输出 JSON 文件路径')

    args = parser.parse_args()

    print("加载结果...")
    stats = analyze_cross_review(Path(args.round1_dir), Path(args.round2_dir))

    print_summary(stats)

    # 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding='utf-8')

    print("\n" + "=" * 80)
    print(f"✅ 分析完成，结果已保存到：{args.output}")
    print("=" * 80)


if __name__ == '__main__':
    main()
