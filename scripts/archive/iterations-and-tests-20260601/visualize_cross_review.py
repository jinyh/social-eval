#!/usr/bin/env python3
"""交叉评审结果可视化脚本

生成对比图表：散点图、箱线图、热力图等。

用法：
    python scripts/visualize_cross_review.py \
        --analysis results/cross-review-analysis.json \
        --output-dir results/cross-review-visualizations
"""

import argparse
import json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

# 设置中文字体
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False


def plot_model_comparison(stats: dict, output_dir: Path):
    """绘制模型对比图"""
    models = list(stats['models'].keys())
    model_labels = {
        'deepseek-v4-pro': 'DeepSeek V4 Pro',
        'glm-5.1': 'GLM-5.1',
        'kimi-k2.6': 'Kimi K2.6',
        'qwen3.6-plus': 'Qwen3.6-Plus'
    }

    # 1. 模型评分变化散点图
    fig, ax = plt.subplots(figsize=(10, 10))

    for model in models:
        model_stat = stats['models'][model]
        round1 = model_stat['round1_mean']
        round2 = model_stat['round2_mean']

        ax.scatter(round1, round2, s=200, alpha=0.7, label=model_labels.get(model, model))
        ax.annotate(model_labels.get(model, model), (round1, round2),
                   xytext=(5, 5), textcoords='offset points', fontsize=10)

    # 绘制 y=x 参考线
    min_val = min(stats['models'][m]['round1_mean'] for m in models)
    max_val = max(stats['models'][m]['round2_mean'] for m in models)
    ax.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.3, label='无变化线')

    ax.set_xlabel('第一轮平均分', fontsize=12)
    ax.set_ylabel('第二轮平均分', fontsize=12)
    ax.set_title('各模型评分变化散点图', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / 'model_score_change_scatter.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'model_score_change_scatter.png'}")
    plt.close()

    # 2. 模型变化方向柱状图
    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(models))
    width = 0.25

    increased = [stats['models'][m]['score_increased'] for m in models]
    decreased = [stats['models'][m]['score_decreased'] for m in models]
    unchanged = [stats['models'][m]['score_unchanged'] for m in models]

    ax.bar(x - width, increased, width, label='上调', color='#4ECDC4')
    ax.bar(x, decreased, width, label='下调', color='#FF6B6B')
    ax.bar(x + width, unchanged, width, label='不变', color='#95A5A6')

    ax.set_xlabel('模型', fontsize=12)
    ax.set_ylabel('次数', fontsize=12)
    ax.set_title('各模型评分变化方向分布', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([model_labels.get(m, m) for m in models], rotation=15)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_dir / 'model_change_direction.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'model_change_direction.png'}")
    plt.close()

    # 3. 模型平均变化对比
    fig, ax = plt.subplots(figsize=(10, 6))

    avg_changes = [stats['models'][m]['avg_change'] for m in models]
    colors = ['#4ECDC4' if c > 0 else '#FF6B6B' for c in avg_changes]

    bars = ax.bar([model_labels.get(m, m) for m in models], avg_changes, color=colors, alpha=0.7)

    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_xlabel('模型', fontsize=12)
    ax.set_ylabel('平均变化（分）', fontsize=12)
    ax.set_title('各模型平均评分变化', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y')

    # 添加数值标签
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{height:+.1f}',
               ha='center', va='bottom' if height > 0 else 'top', fontsize=10)

    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(output_dir / 'model_avg_change.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'model_avg_change.png'}")
    plt.close()


def plot_dimension_comparison(stats: dict, output_dir: Path):
    """绘制维度对比图"""
    dimensions = list(stats['dimensions'].keys())

    # 1. 维度收敛性改善热力图
    fig, ax = plt.subplots(figsize=(10, 6))

    convergence_improvements = [stats['dimensions'][d]['avg_convergence_improvement'] for d in dimensions]

    colors = ['#4ECDC4' if c > 0 else '#FF6B6B' for c in convergence_improvements]
    bars = ax.barh(dimensions, convergence_improvements, color=colors, alpha=0.7)

    ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_xlabel('收敛性改善（std 降低）', fontsize=12)
    ax.set_ylabel('维度', fontsize=12)
    ax.set_title('各维度收敛性改善', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='x')

    # 添加数值标签
    for bar in bars:
        width = bar.get_width()
        ax.text(width, bar.get_y() + bar.get_height()/2.,
               f'{width:+.1f}',
               ha='left' if width > 0 else 'right', va='center', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_dir / 'dimension_convergence.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'dimension_convergence.png'}")
    plt.close()

    # 2. 维度平均变化
    fig, ax = plt.subplots(figsize=(10, 6))

    avg_changes = [stats['dimensions'][d]['avg_change'] for d in dimensions]
    colors = ['#4ECDC4' if c > 0 else '#FF6B6B' for c in avg_changes]

    bars = ax.barh(dimensions, avg_changes, color=colors, alpha=0.7)

    ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_xlabel('平均变化（分）', fontsize=12)
    ax.set_ylabel('维度', fontsize=12)
    ax.set_title('各维度平均评分变化', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='x')

    # 添加数值标签
    for bar in bars:
        width = bar.get_width()
        ax.text(width, bar.get_y() + bar.get_height()/2.,
               f'{width:+.1f}',
               ha='left' if width > 0 else 'right', va='center', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_dir / 'dimension_avg_change.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'dimension_avg_change.png'}")
    plt.close()


def plot_group_comparison(stats: dict, output_dir: Path):
    """绘制分组对比图"""
    fig, ax = plt.subplots(figsize=(10, 6))

    groups = ['A 组\n(GLM + Qwen)', 'B 组\n(DeepSeek + Kimi)']
    avg_changes = [
        stats['groups']['a_group']['avg_change'],
        stats['groups']['b_group']['avg_change']
    ]
    colors = ['#4ECDC4', '#FF6B6B']

    bars = ax.bar(groups, avg_changes, color=colors, alpha=0.7, width=0.5)

    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_ylabel('平均变化（分）', fontsize=12)
    ax.set_title('A 组 vs B 组平均评分变化', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y')

    # 添加数值标签
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{height:+.1f}',
               ha='center', va='bottom' if height > 0 else 'top', fontsize=12, fontweight='bold')

    plt.tight_layout()
    plt.savefig(output_dir / 'group_comparison.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'group_comparison.png'}")
    plt.close()


def plot_overall_summary(stats: dict, output_dir: Path):
    """绘制总体摘要图"""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('交叉评审结果总体摘要', fontsize=16, fontweight='bold')

    # 1. 总体评分变化
    overall = stats['overall']
    categories = ['第一轮', '第二轮']
    values = [overall['avg_round1_mean'], overall['avg_round2_mean']]

    bars = ax1.bar(categories, values, color=['#95A5A6', '#4ECDC4'], alpha=0.7, width=0.5)
    ax1.set_ylabel('平均分', fontsize=12)
    ax1.set_title('总体平均分对比', fontsize=12, fontweight='bold')
    ax1.set_ylim(0, 100)
    ax1.grid(True, alpha=0.3, axis='y')

    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}',
                ha='center', va='bottom', fontsize=12, fontweight='bold')

    # 2. 分组对比
    groups = ['A 组', 'B 组']
    avg_changes = [
        stats['groups']['a_group']['avg_change'],
        stats['groups']['b_group']['avg_change']
    ]
    colors = ['#4ECDC4' if c > 0 else '#FF6B6B' for c in avg_changes]

    bars = ax2.bar(groups, avg_changes, color=colors, alpha=0.7, width=0.5)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax2.set_ylabel('平均变化（分）', fontsize=12)
    ax2.set_title('分组平均变化', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')

    for bar in bars:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:+.1f}',
                ha='center', va='bottom' if height > 0 else 'top', fontsize=12, fontweight='bold')

    # 3. 各模型修改率
    models = list(stats['models'].keys())
    model_labels = {
        'deepseek-v4-pro': 'DeepSeek',
        'glm-5.1': 'GLM-5.1',
        'kimi-k2.6': 'Kimi',
        'qwen3.6-plus': 'Qwen'
    }
    change_rates = [stats['models'][m]['change_rate'] for m in models]

    bars = ax3.bar([model_labels.get(m, m) for m in models], change_rates,
                   color='#45B7D1', alpha=0.7)
    ax3.set_ylabel('修改率 (%)', fontsize=12)
    ax3.set_title('各模型修改率', fontsize=12, fontweight='bold')
    ax3.set_ylim(0, 100)
    ax3.grid(True, alpha=0.3, axis='y')
    ax3.tick_params(axis='x', rotation=15)

    for bar in bars:
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}%',
                ha='center', va='bottom', fontsize=10)

    # 4. 论文数统计
    total_papers = stats['total_papers']
    ax4.text(0.5, 0.5, f'总论文数\n\n{total_papers}',
            ha='center', va='center', fontsize=32, fontweight='bold',
            transform=ax4.transAxes)
    ax4.axis('off')

    plt.tight_layout()
    plt.savefig(output_dir / 'overall_summary.png', dpi=300, bbox_inches='tight')
    print(f"✅ 已保存：{output_dir / 'overall_summary.png'}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='交叉评审结果可视化')
    parser.add_argument('--analysis', required=True, help='分析结果 JSON 文件路径')
    parser.add_argument('--output-dir', required=True, help='输出目录')

    args = parser.parse_args()

    # 加载分析结果
    with open(args.analysis, 'r', encoding='utf-8') as f:
        stats = json.load(f)

    # 创建输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("生成可视化图表...")

    # 生成各类图表
    plot_overall_summary(stats, output_dir)
    plot_model_comparison(stats, output_dir)
    plot_dimension_comparison(stats, output_dir)
    plot_group_comparison(stats, output_dir)

    print("\n" + "=" * 80)
    print(f"✅ 可视化完成！图表已保存到：{output_dir}")
    print("=" * 80)


if __name__ == '__main__':
    main()
