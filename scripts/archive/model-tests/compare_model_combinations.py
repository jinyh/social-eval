"""对比不同模型组合的标准差

分析现有测试结果，对比：
1. 三模型（GLM + Qwen + DeepSeek）
2. 三模型（GPT + GLM + Qwen）
3. 双模型（GLM + Qwen）
4. 单模型（GPT-5.4）

用法：
    python scripts/compare_model_combinations.py results/regression-v2.42-sample1.json
"""

import argparse
import json
import statistics
from pathlib import Path


def calculate_std_for_models(scores_dict, model_names):
    """计算指定模型组合的标准差"""
    scores = [scores_dict[m] for m in model_names if m in scores_dict]
    if len(scores) < 2:
        return None
    return statistics.stdev(scores)


def analyze_result_file(file_path: str):
    """分析单个结果文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"\n{'='*80}")
    print(f"文件: {Path(file_path).name}")
    print(f"论文: {Path(data['paper']).name}")
    print(f"框架: {data.get('framework_version', 'unknown')}")
    print(f"{'='*80}\n")

    # 获取所有模型
    all_models = data.get('models', [])
    print(f"可用模型: {', '.join(all_models)}\n")

    # 定义要对比的模型组合
    combinations = {
        "三模型(GLM+Qwen+DeepSeek)": ["glm-5.1", "qwen3.6-plus", "deepseek-v4-pro"],
        "三模型(GPT+GLM+Qwen)": ["gpt-5.4", "glm-5.1", "qwen3.6-plus"],
        "双模型(GLM+Qwen)": ["glm-5.1", "qwen3.6-plus"],
        "双模型(GPT+GLM)": ["gpt-5.4", "glm-5.1"],
        "双模型(GPT+Qwen)": ["gpt-5.4", "qwen3.6-plus"],
        "单模型(GPT-5.4)": ["gpt-5.4"],
    }

    # 分析每个组合
    results = {}
    for combo_name, models in combinations.items():
        # 检查模型是否都存在
        available_models = [m for m in models if m in all_models]
        if len(available_models) < len(models):
            continue

        dimension_stds = []
        dimension_details = []

        for dim_name, dim_data in data['dimensions'].items():
            scores = dim_data['scores']
            std = calculate_std_for_models(scores, models)

            if std is not None:
                dimension_stds.append(std)
                dimension_details.append({
                    'name': dim_data['name_zh'],
                    'std': std,
                    'scores': {m: scores[m] for m in models if m in scores}
                })

        if dimension_stds:
            avg_std = statistics.mean(dimension_stds)
            max_std = max(dimension_stds)

            results[combo_name] = {
                'avg_std': avg_std,
                'max_std': max_std,
                'dimensions': dimension_details
            }

    # 按平均标准差排序
    sorted_results = sorted(results.items(), key=lambda x: x[1]['avg_std'])

    print(f"{'模型组合':<30s} {'平均std':>10s} {'最大std':>10s} {'评价':>10s}")
    print("-" * 80)

    for combo_name, stats in sorted_results:
        avg_std = stats['avg_std']
        max_std = stats['max_std']

        # 评价
        if avg_std < 5:
            rating = "✓ 优秀"
        elif avg_std < 8:
            rating = "○ 良好"
        elif avg_std < 12:
            rating = "△ 一般"
        else:
            rating = "✗ 较差"

        print(f"{combo_name:<30s} {avg_std:>10.1f} {max_std:>10.1f} {rating:>10s}")

    # 详细展示最佳组合
    if sorted_results:
        best_combo, best_stats = sorted_results[0]
        print(f"\n{'='*80}")
        print(f"最佳组合: {best_combo}")
        print(f"平均标准差: {best_stats['avg_std']:.1f}")
        print(f"{'='*80}\n")

        print(f"{'维度':<15s} {'标准差':>10s} {'分数分布':<40s}")
        print("-" * 80)
        for dim in best_stats['dimensions']:
            scores_str = ', '.join([f"{m.split('-')[0]}:{s}" for m, s in dim['scores'].items()])
            print(f"{dim['name']:<15s} {dim['std']:>10.1f} {scores_str:<40s}")

    return results


def main():
    parser = argparse.ArgumentParser(description="对比不同模型组合的标准差")
    parser.add_argument("files", nargs="+", help="结果文件路径")

    args = parser.parse_args()

    all_results = {}
    for file_path in args.files:
        try:
            results = analyze_result_file(file_path)
            all_results[file_path] = results
        except Exception as e:
            print(f"❌ 处理文件 {file_path} 时出错: {e}")

    # 如果有多个文件，输出汇总
    if len(all_results) > 1:
        print(f"\n{'='*80}")
        print("汇总：各模型组合在所有测试中的平均表现")
        print(f"{'='*80}\n")

        # 收集所有组合的平均标准差
        combo_stats = {}
        for file_path, results in all_results.items():
            for combo_name, stats in results.items():
                if combo_name not in combo_stats:
                    combo_stats[combo_name] = []
                combo_stats[combo_name].append(stats['avg_std'])

        # 计算每个组合的总体平均
        print(f"{'模型组合':<30s} {'平均std':>10s} {'测试数':>10s}")
        print("-" * 80)

        sorted_combos = sorted(combo_stats.items(), key=lambda x: statistics.mean(x[1]))
        for combo_name, stds in sorted_combos:
            avg = statistics.mean(stds)
            count = len(stds)
            print(f"{combo_name:<30s} {avg:>10.1f} {count:>10d}")


if __name__ == "__main__":
    main()
