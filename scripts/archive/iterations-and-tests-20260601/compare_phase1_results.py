#!/usr/bin/env python3
"""
对比 phase1-100-papers（双模型）和 phase1-100-papers-strictest（四模型严格版）的评分差异
"""

import json
from pathlib import Path
from typing import Dict, List
import statistics

def load_results(result_dir: Path) -> List[Dict]:
    """加载指定目录下的所有评价结果"""
    results = []
    for json_file in sorted(result_dir.glob("paper-*.json")):
        with open(json_file, 'r', encoding='utf-8') as f:
            results.append(json.load(f))
    return results

def extract_scores(result: Dict) -> Dict:
    """提取评分数据"""
    scores = {
        'paper': result.get('paper', ''),
        'models': result.get('models', []),
        'dimensions': {}
    }

    # 提取六维评分
    if 'dimensions' in result:
        for dim_name, dim_data in result['dimensions'].items():
            if isinstance(dim_data, dict):
                # 双模型结构：直接有 mean/median/std
                if 'mean' in dim_data:
                    scores['dimensions'][dim_name] = {
                        'mean': dim_data.get('mean'),
                        'median': dim_data.get('median'),
                        'std': dim_data.get('std'),
                        'model_scores': dim_data.get('model_scores', {})
                    }
                # 四模型结构：有 aggregation_mean 和 aggregation_strictest
                elif 'aggregation_mean' in dim_data:
                    scores['dimensions'][dim_name] = {
                        'mean': dim_data['aggregation_mean'].get('mean'),
                        'median': dim_data['aggregation_mean'].get('median'),
                        'std': dim_data.get('std'),
                        'model_scores': dim_data.get('model_scores', {})
                    }

    # 提取总分
    if 'overall' in result:
        overall = result['overall']
        # 双模型结构：直接有 final_score
        if 'final_score' in overall and isinstance(overall['final_score'], (int, float)):
            scores['final_mean'] = overall['final_score']
            scores['final_std'] = overall.get('avg_std')
        # 四模型结构：有 aggregation_mean
        elif 'aggregation_mean' in overall:
            scores['final_mean'] = overall['aggregation_mean'].get('final_score')
            scores['final_std'] = overall.get('avg_std')

    return scores

def compare_results(two_model_dir: Path, four_model_dir: Path):
    """对比两个测试结果"""
    print("=" * 80)
    print("Phase 1 评分对比分析：双模型 vs 四模型严格版")
    print("=" * 80)

    two_model_results = load_results(two_model_dir)
    four_model_results = load_results(four_model_dir)

    print(f"\n双模型测试：{len(two_model_results)} 篇论文")
    print(f"四模型严格版：{len(four_model_results)} 篇论文")

    if len(two_model_results) != len(four_model_results):
        print("\n⚠️  警告：两个测试的论文数量不一致")
        return

    # 提取模型信息
    two_models = two_model_results[0].get('models', [])
    four_models = four_model_results[0].get('models', [])

    print(f"\n双模型配置：{', '.join(two_models)}")
    print(f"四模型配置：{', '.join(four_models)}")

    # 统计总分差异
    two_model_means = []
    four_model_means = []
    score_diffs = []

    for two_res, four_res in zip(two_model_results, four_model_results):
        two_score = extract_scores(two_res)
        four_score = extract_scores(four_res)

        if two_score.get('final_mean') and four_score.get('final_mean'):
            two_model_means.append(two_score['final_mean'])
            four_model_means.append(four_score['final_mean'])
            score_diffs.append(four_score['final_mean'] - two_score['final_mean'])

    print("\n" + "=" * 80)
    print("总分统计")
    print("=" * 80)
    print(f"双模型均值：{statistics.mean(two_model_means):.2f} ± {statistics.stdev(two_model_means):.2f}")
    print(f"四模型均值：{statistics.mean(four_model_means):.2f} ± {statistics.stdev(four_model_means):.2f}")
    print(f"平均降分：{statistics.mean(score_diffs):.2f} ± {statistics.stdev(score_diffs):.2f}")
    print(f"降分范围：[{min(score_diffs):.2f}, {max(score_diffs):.2f}]")

    # 统计各维度差异
    print("\n" + "=" * 80)
    print("各维度评分对比")
    print("=" * 80)

    dimension_names = [
        'question_innovation',
        'analytical_framework',
        'evidence_quality',
        'conclusion_acceptability',
        'forward_extensibility',
        'citation_quality'
    ]

    for dim_name in dimension_names:
        two_dim_scores = []
        four_dim_scores = []
        dim_diffs = []

        for two_res, four_res in zip(two_model_results, four_model_results):
            two_score = extract_scores(two_res)
            four_score = extract_scores(four_res)

            if dim_name in two_score['dimensions'] and dim_name in four_score['dimensions']:
                two_mean = two_score['dimensions'][dim_name]['mean']
                four_mean = four_score['dimensions'][dim_name]['mean']

                if two_mean is not None and four_mean is not None:
                    two_dim_scores.append(two_mean)
                    four_dim_scores.append(four_mean)
                    dim_diffs.append(four_mean - two_mean)

        if dim_diffs:
            print(f"\n{dim_name}:")
            print(f"  双模型：{statistics.mean(two_dim_scores):.2f} ± {statistics.stdev(two_dim_scores):.2f}")
            print(f"  四模型：{statistics.mean(four_dim_scores):.2f} ± {statistics.stdev(four_dim_scores):.2f}")
            print(f"  平均降分：{statistics.mean(dim_diffs):.2f} ± {statistics.stdev(dim_diffs):.2f}")

    # 分析各模型的评分分布
    print("\n" + "=" * 80)
    print("各模型评分分布分析")
    print("=" * 80)

    model_scores = {model: [] for model in four_models}

    for four_res in four_model_results:
        four_score = extract_scores(four_res)
        for dim_name in dimension_names:
            if dim_name in four_score['dimensions']:
                for model, score in four_score['dimensions'][dim_name]['model_scores'].items():
                    if score is not None:
                        model_scores[model].append(score)

    for model in four_models:
        if model_scores[model]:
            print(f"\n{model}:")
            print(f"  均值：{statistics.mean(model_scores[model]):.2f}")
            print(f"  标准差：{statistics.stdev(model_scores[model]):.2f}")
            print(f"  中位数：{statistics.median(model_scores[model]):.2f}")
            print(f"  范围：[{min(model_scores[model]):.2f}, {max(model_scores[model]):.2f}]")

    # 检查 DeepSeek 是否系统性偏低
    print("\n" + "=" * 80)
    print("DeepSeek 偏低分析")
    print("=" * 80)

    if 'deepseek-v4-pro' in model_scores:
        deepseek_mean = statistics.mean(model_scores['deepseek-v4-pro'])
        other_models_means = []

        for model in four_models:
            if model != 'deepseek-v4-pro' and model_scores[model]:
                other_models_means.append(statistics.mean(model_scores[model]))

        if other_models_means:
            other_mean = statistics.mean(other_models_means)
            print(f"DeepSeek 均值：{deepseek_mean:.2f}")
            print(f"其他模型均值：{other_mean:.2f}")
            print(f"差距：{deepseek_mean - other_mean:.2f}")

            if deepseek_mean < other_mean - 5:
                print("\n⚠️  DeepSeek 系统性偏低（差距 > 5 分）")
            else:
                print("\n✅ DeepSeek 评分在合理范围内")

    # 输出降分最多的论文
    print("\n" + "=" * 80)
    print("降分最多的 10 篇论文")
    print("=" * 80)

    paper_diffs = []
    for two_res, four_res in zip(two_model_results, four_model_results):
        two_score = extract_scores(two_res)
        four_score = extract_scores(four_res)

        if two_score.get('final_mean') and four_score.get('final_mean'):
            paper_name = Path(two_score['paper']).name
            diff = four_score['final_mean'] - two_score['final_mean']
            paper_diffs.append((paper_name, two_score['final_mean'], four_score['final_mean'], diff))

    paper_diffs.sort(key=lambda x: x[3])

    for i, (paper, two_score, four_score, diff) in enumerate(paper_diffs[:10], 1):
        print(f"{i}. {paper}")
        print(f"   双模型：{two_score:.2f} → 四模型：{four_score:.2f} (降分 {abs(diff):.2f})")

if __name__ == '__main__':
    two_model_dir = Path('results/phase1-100-papers')
    four_model_dir = Path('results/phase1-100-papers-strictest')

    compare_results(two_model_dir, four_model_dir)
