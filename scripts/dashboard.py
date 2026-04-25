#!/usr/bin/env python3
"""Autoresearch 进度仪表板"""

import json
import sys
from pathlib import Path
from datetime import datetime

def load_log(log_file):
    """加载迭代日志"""
    iterations = []
    with open(log_file) as f:
        lines = f.readlines()[1:]  # 跳过表头
        for line in lines:
            parts = line.strip().split('\t')
            if len(parts) >= 10:
                iterations.append({
                    'iteration': int(parts[0]),
                    'timestamp': parts[1],
                    'version': parts[2],
                    'description': parts[3],
                    'avg_std': float(parts[4]),
                    'max_std': float(parts[5]),
                    'high_confidence_pct': float(parts[6]),
                    'composite_score': float(parts[7]),
                    'decision': parts[8],
                    'notes': parts[9] if len(parts) > 9 else ''
                })
    return iterations

def calculate_progress(iterations):
    """计算进度"""
    if not iterations:
        return None

    baseline = iterations[0]
    current = iterations[-1]

    # 目标
    target_avg_std = 5.0
    target_high_confidence = 80.0
    target_composite = -target_avg_std + 10 * (target_high_confidence / 100)

    # 当前进度
    avg_std_progress = (baseline['avg_std'] - current['avg_std']) / (baseline['avg_std'] - target_avg_std) * 100
    hc_progress = (current['high_confidence_pct'] - baseline['high_confidence_pct']) / (target_high_confidence - baseline['high_confidence_pct']) * 100
    composite_progress = (current['composite_score'] - baseline['composite_score']) / (target_composite - baseline['composite_score']) * 100

    return {
        'baseline': baseline,
        'current': current,
        'target': {
            'avg_std': target_avg_std,
            'high_confidence_pct': target_high_confidence,
            'composite_score': target_composite
        },
        'progress': {
            'avg_std': avg_std_progress,
            'high_confidence': hc_progress,
            'composite': composite_progress
        }
    }

def print_dashboard(log_file):
    """打印仪表板"""
    iterations = load_log(log_file)
    if not iterations:
        print("❌ 没有找到迭代记录")
        return

    progress = calculate_progress(iterations)

    print("=" * 70)
    print("🚀 AUTORESEARCH 进度仪表板")
    print("=" * 70)
    print()

    # 基本信息
    print(f"📅 开始时间: {iterations[0]['timestamp']}")
    print(f"📅 最新更新: {iterations[-1]['timestamp']}")
    print(f"🔢 已完成迭代: {len(iterations) - 1} / 20")
    print()

    # 当前状态
    current = progress['current']
    print("📊 当前状态:")
    print(f"  版本: {current['version']}")
    print(f"  平均标准差: {current['avg_std']:.1f}")
    print(f"  最大标准差: {current['max_std']:.1f}")
    print(f"  高置信度比例: {current['high_confidence_pct']:.1f}%")
    print(f"  复合评分: {current['composite_score']:.2f}")
    print()

    # 目标
    target = progress['target']
    print("🎯 目标:")
    print(f"  平均标准差: < {target['avg_std']:.1f}")
    print(f"  高置信度比例: > {target['high_confidence_pct']:.1f}%")
    print(f"  复合评分: > {target['composite_score']:.2f}")
    print()

    # 进度
    prog = progress['progress']
    print("📈 进度:")
    print(f"  平均标准差: {prog['avg_std']:.1f}%")
    print(f"  高置信度比例: {prog['high_confidence']:.1f}%")
    print(f"  复合评分: {prog['composite']:.1f}%")
    print()

    # 改进历史
    print("📜 改进历史:")
    for i, iter_data in enumerate(iterations):
        if i == 0:
            print(f"  [{iter_data['iteration']}] {iter_data['version']} - BASELINE")
        else:
            delta = iter_data['composite_score'] - iterations[i-1]['composite_score']
            decision_icon = "✅" if iter_data['decision'] == 'keep' else "❌"
            print(f"  [{iter_data['iteration']}] {iter_data['version']} - {decision_icon} {iter_data['decision'].upper()} (Δ{delta:+.2f})")
            print(f"      {iter_data['description']}")
    print()

    # 预测
    if len(iterations) > 1:
        total_improvement = current['composite_score'] - progress['baseline']['composite_score']
        avg_improvement_per_iter = total_improvement / (len(iterations) - 1)
        remaining_improvement = target['composite_score'] - current['composite_score']
        estimated_iters = remaining_improvement / avg_improvement_per_iter if avg_improvement_per_iter > 0 else float('inf')

        print("🔮 预测:")
        print(f"  平均每次改进: {avg_improvement_per_iter:+.2f}")
        print(f"  还需改进: {remaining_improvement:+.2f}")
        print(f"  预计还需迭代: {estimated_iters:.0f} 次")
        print()

    print("=" * 70)

if __name__ == "__main__":
    log_file = "results/autoresearch/autoresearch-log-20260425-090828.tsv"
    if len(sys.argv) > 1:
        log_file = sys.argv[1]

    print_dashboard(log_file)
