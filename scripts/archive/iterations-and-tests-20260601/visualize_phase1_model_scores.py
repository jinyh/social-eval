#!/usr/bin/env python3
"""
可视化 Phase 1 四模型测试中各维度的模型打分分布
"""

import json
from pathlib import Path
from typing import Dict, List
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
from collections import defaultdict

# 设置中文字体
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

def load_results(result_dir: Path) -> List[Dict]:
    """加载指定目录下的所有评价结果"""
    results = []
    for json_file in sorted(result_dir.glob("paper-*.json")):
        with open(json_file, 'r', encoding='utf-8') as f:
            results.append(json.load(f))
    return results

def extract_model_scores_by_dimension(results: List[Dict]) -> Dict:
    """提取各维度各模型的评分"""
    dimension_names = {
        'problem_originality': '问题创新性',
        'literature_insight': '文献洞察力',
        'analytical_framework': '分析框架',
        'logical_coherence': '逻辑连贯性',
        'conclusion_consensus': '结论共识度',
        'forward_extension': '前瞻延展性'
    }

    # 结构：{dimension: {model: [scores]}}
    data = defaultdict(lambda: defaultdict(list))

    for result in results:
        if 'dimensions' not in result:
            continue

        for dim_key, dim_name in dimension_names.items():
            if dim_key not in result['dimensions']:
                continue

            dim_data = result['dimensions'][dim_key]
            if 'model_scores' not in dim_data:
                continue

            for model, score in dim_data['model_scores'].items():
                if score is not None:
                    data[dim_name][model].append(score)

    return data

def plot_model_comparison(data: Dict, output_dir: Path):
    """绘制各维度模型对比图"""
    output_dir.mkdir(parents=True, exist_ok=True)

    models = ['deepseek-v4-pro', 'glm-5.1', 'kimi-k2.6', 'qwen3.6-plus']
    model_labels = {
        'deepseek-v4-pro': 'DeepSeek V4 Pro',
        'glm-5.1': 'GLM-5.1',
        'kimi-k2.6': 'Kimi K2.6',
        'qwen3.6-plus': 'Qwen3.6-Plus'
    }
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A']

    # 1. 各维度箱线图对比
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('各维度模型评分分布对比（箱线图）', fontsize=16, fontweight='bold')

    for idx, (dim_name, dim_data) in enumerate(data.items()):
        ax = axes[idx // 3, idx % 3]

        # 准备数据
        plot_data = []
        plot_labels = []
        for model in models:
            if model in dim_data and dim_data[model]:
                plot_data.append(dim_data[model])
                plot_labels.append(model_labels[model])

        # 绘制箱线图
        bp = ax.boxplot(plot_data, labels=plot_labels, patch_artist=True,
                        showmeans=True, meanline=True)

        # 设置颜色
        for patch, color in zip(bp['boxes'], colors[:len(plot_data)]):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)

        ax.set_title(dim_name, fontsize=12, fontweight='bold')
        ax.set_ylabel('评分', fontsize=10)
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3, axis='y')
        ax.tick_params(axis='x', rotation=15)

    plt.tight_layout()
    plt.savefig(output_dir / 'dimension_boxplot.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'dimension_boxplot.png'}")
    plt.close()

    # 2. 各维度小提琴图对比
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('各维度模型评分分布对比（小提琴图）', fontsize=16, fontweight='bold')

    for idx, (dim_name, dim_data) in enumerate(data.items()):
        ax = axes[idx // 3, idx % 3]

        # 准备数据
        plot_data = []
        plot_labels = []
        for model in models:
            if model in dim_data and dim_data[model]:
                plot_data.append(dim_data[model])
                plot_labels.append(model_labels[model])

        # 绘制小提琴图
        parts = ax.violinplot(plot_data, positions=range(len(plot_data)),
                             showmeans=True, showmedians=True)

        # 设置颜色
        for pc, color in zip(parts['bodies'], colors[:len(plot_data)]):
            pc.set_facecolor(color)
            pc.set_alpha(0.6)

        ax.set_title(dim_name, fontsize=12, fontweight='bold')
        ax.set_ylabel('评分', fontsize=10)
        ax.set_ylim(0, 100)
        ax.set_xticks(range(len(plot_labels)))
        ax.set_xticklabels(plot_labels, rotation=15)
        ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_dir / 'dimension_violin.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'dimension_violin.png'}")
    plt.close()

    # 3. 模型均值对比雷达图
    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))

    dimensions = list(data.keys())
    angles = np.linspace(0, 2 * np.pi, len(dimensions), endpoint=False).tolist()
    angles += angles[:1]  # 闭合

    for model, color in zip(models, colors):
        means = []
        for dim_name in dimensions:
            if model in data[dim_name] and data[dim_name][model]:
                means.append(np.mean(data[dim_name][model]))
            else:
                means.append(0)
        means += means[:1]  # 闭合

        ax.plot(angles, means, 'o-', linewidth=2, label=model_labels[model], color=color)
        ax.fill(angles, means, alpha=0.15, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dimensions, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_title('各模型在六维度上的平均评分对比', fontsize=14, fontweight='bold', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
    ax.grid(True)

    plt.tight_layout()
    plt.savefig(output_dir / 'model_radar.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'model_radar.png'}")
    plt.close()

    # 4. 模型评分分布直方图
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('各模型评分分布直方图（所有维度汇总）', fontsize=16, fontweight='bold')

    for idx, (model, color) in enumerate(zip(models, colors)):
        ax = axes[idx // 2, idx % 2]

        # 汇总该模型在所有维度的评分
        all_scores = []
        for dim_data in data.values():
            if model in dim_data:
                all_scores.extend(dim_data[model])

        if all_scores:
            ax.hist(all_scores, bins=20, color=color, alpha=0.7, edgecolor='black')
            ax.axvline(np.mean(all_scores), color='red', linestyle='--', linewidth=2,
                      label=f'均值: {np.mean(all_scores):.1f}')
            ax.axvline(np.median(all_scores), color='blue', linestyle='--', linewidth=2,
                      label=f'中位数: {np.median(all_scores):.1f}')

            ax.set_title(model_labels[model], fontsize=12, fontweight='bold')
            ax.set_xlabel('评分', fontsize=10)
            ax.set_ylabel('频次', fontsize=10)
            ax.set_xlim(0, 100)
            ax.legend()
            ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_dir / 'model_histogram.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'model_histogram.png'}")
    plt.close()

    # 5. 模型间相关性热力图
    fig, ax = plt.subplots(figsize=(10, 8))

    # 计算相关性矩阵
    correlation_matrix = np.zeros((len(models), len(models)))
    for i, model1 in enumerate(models):
        for j, model2 in enumerate(models):
            scores1 = []
            scores2 = []
            for dim_data in data.values():
                if model1 in dim_data and model2 in dim_data:
                    s1 = dim_data[model1]
                    s2 = dim_data[model2]
                    min_len = min(len(s1), len(s2))
                    scores1.extend(s1[:min_len])
                    scores2.extend(s2[:min_len])

            if scores1 and scores2:
                correlation_matrix[i, j] = np.corrcoef(scores1, scores2)[0, 1]

    im = ax.imshow(correlation_matrix, cmap='RdYlGn', vmin=0, vmax=1)

    # 设置刻度
    ax.set_xticks(range(len(models)))
    ax.set_yticks(range(len(models)))
    ax.set_xticklabels([model_labels[m] for m in models], rotation=45, ha='right')
    ax.set_yticklabels([model_labels[m] for m in models])

    # 添加数值标注
    for i in range(len(models)):
        for j in range(len(models)):
            text = ax.text(j, i, f'{correlation_matrix[i, j]:.2f}',
                          ha="center", va="center", color="black", fontsize=12)

    ax.set_title('模型间评分相关性热力图', fontsize=14, fontweight='bold', pad=20)
    plt.colorbar(im, ax=ax, label='相关系数')

    plt.tight_layout()
    plt.savefig(output_dir / 'model_correlation.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'model_correlation.png'}")
    plt.close()

def print_statistics(data: Dict):
    """打印统计信息"""
    print("\n" + "=" * 80)
    print("各维度各模型统计信息")
    print("=" * 80)

    models = ['deepseek-v4-pro', 'glm-5.1', 'kimi-k2.6', 'qwen3.6-plus']
    model_labels = {
        'deepseek-v4-pro': 'DeepSeek',
        'glm-5.1': 'GLM-5.1',
        'kimi-k2.6': 'Kimi',
        'qwen3.6-plus': 'Qwen'
    }

    for dim_name, dim_data in data.items():
        print(f"\n【{dim_name}】")
        print(f"{'模型':<15} {'均值':<8} {'中位数':<8} {'标准差':<8} {'最小值':<8} {'最大值':<8} {'样本数':<8}")
        print("-" * 80)

        for model in models:
            if model in dim_data and dim_data[model]:
                scores = dim_data[model]
                print(f"{model_labels[model]:<15} "
                      f"{np.mean(scores):<8.2f} "
                      f"{np.median(scores):<8.2f} "
                      f"{np.std(scores):<8.2f} "
                      f"{min(scores):<8.2f} "
                      f"{max(scores):<8.2f} "
                      f"{len(scores):<8}")

if __name__ == '__main__':
    result_dir = Path('results/phase1-100-papers-strictest')
    output_dir = Path('results/phase1-100-papers-strictest/visualizations')

    print("加载测试结果...")
    results = load_results(result_dir)
    print(f"已加载 {len(results)} 篇论文的评价结果")

    print("\n提取各维度模型评分...")
    data = extract_model_scores_by_dimension(results)

    print("\n生成可视化图表...")
    plot_model_comparison(data, output_dir)

    print_statistics(data)

    print("\n" + "=" * 80)
    print("✅ 可视化完成！")
    print(f"📊 图表保存在：{output_dir}")
    print("=" * 80)
