#!/usr/bin/env python3
"""分析 autoresearch 迭代结果"""

import json
import sys
from pathlib import Path

def analyze_result(result_file):
    """分析单次验证结果"""
    with open(result_file) as f:
        data = json.load(f)

    overall = data['overall']
    dimensions = data['dimensions']

    print(f"\n{'='*60}")
    print(f"框架: {data['framework']}")
    print(f"版本: {data.get('framework_version', 'unknown')}")
    print(f"{'='*60}")

    print(f"\n整体指标:")
    print(f"  平均标准差: {overall['avg_std']:.1f}")
    print(f"  最大标准差: {overall['max_std']:.1f} ({overall['worst_dimension']})")
    print(f"  高置信度比例: {overall['high_confidence_pct']:.1f}%")
    print(f"  复合评分: {overall['composite_score']:.2f}")

    print(f"\n各维度标准差:")
    for dim_key, dim_data in dimensions.items():
        std = dim_data['std']
        confidence = dim_data['confidence']
        name = dim_data['name_zh']

        # 标记问题维度
        marker = ""
        if std > 12:
            marker = " ⚠️ CRITICAL"
        elif std > 8:
            marker = " ⚠️ HIGH"
        elif std > 5:
            marker = " ⚠️ MEDIUM"

        print(f"  {name:12s}: std={std:5.1f}, confidence={confidence:8s}{marker}")

        # 显示模型评分
        scores = dim_data['scores']
        print(f"    模型评分: {', '.join([f'{k}={v}' for k, v in scores.items()])}")

    return overall

def compare_results(baseline_file, current_file):
    """对比两次结果"""
    with open(baseline_file) as f:
        baseline = json.load(f)
    with open(current_file) as f:
        current = json.load(f)

    print(f"\n{'='*60}")
    print("对比分析")
    print(f"{'='*60}")

    b_overall = baseline['overall']
    c_overall = current['overall']

    # 整体指标对比
    avg_std_delta = c_overall['avg_std'] - b_overall['avg_std']
    max_std_delta = c_overall['max_std'] - b_overall['max_std']
    hc_pct_delta = c_overall['high_confidence_pct'] - b_overall['high_confidence_pct']
    composite_delta = c_overall['composite_score'] - b_overall['composite_score']

    print(f"\n整体指标变化:")
    print(f"  平均标准差: {b_overall['avg_std']:.1f} → {c_overall['avg_std']:.1f} ({avg_std_delta:+.1f})")
    print(f"  最大标准差: {b_overall['max_std']:.1f} → {c_overall['max_std']:.1f} ({max_std_delta:+.1f})")
    print(f"  高置信度比例: {b_overall['high_confidence_pct']:.1f}% → {c_overall['high_confidence_pct']:.1f}% ({hc_pct_delta:+.1f}%)")
    print(f"  复合评分: {b_overall['composite_score']:.2f} → {c_overall['composite_score']:.2f} ({composite_delta:+.2f})")

    # 判断是否改进
    improved = composite_delta > 0
    decision = "✅ KEEP" if improved else "❌ DISCARD"

    print(f"\n决策: {decision}")

    if improved:
        print(f"  改进幅度: {composite_delta:+.2f}")
    else:
        print(f"  退化幅度: {composite_delta:+.2f}")

    return improved, composite_delta

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python analyze_iteration.py <result_file> [baseline_file]")
        sys.exit(1)

    result_file = sys.argv[1]

    # 分析当前结果
    analyze_result(result_file)

    # 如果提供了基线，进行对比
    if len(sys.argv) >= 3:
        baseline_file = sys.argv[2]
        compare_results(baseline_file, result_file)
