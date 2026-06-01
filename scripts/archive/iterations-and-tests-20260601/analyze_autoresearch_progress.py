#!/usr/bin/env python3
"""
分析 autoresearch 迭代进度
"""
import json
import sys
from pathlib import Path
from datetime import datetime

def analyze_results(results_dir: Path):
    """分析所有测试结果"""
    result_files = sorted(results_dir.glob("quick-verify-*.json"))

    if not result_files:
        print(f"未找到测试结果文件：{results_dir}")
        return

    print(f"找到 {len(result_files)} 个测试结果")
    print("="*80)

    # 按时间排序
    results = []
    for f in result_files:
        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
            results.append({
                'file': f.name,
                'timestamp': data.get('timestamp', ''),
                'avg_std': data['overall']['avg_std'],
                'high_confidence_ratio': data['overall']['high_confidence_ratio'],
                'composite_score': data['overall']['composite_score'],
                'dimensions': data.get('dimensions', {})
            })

    # 打印趋势
    print(f"{'序号':<6} {'时间':<20} {'平均std':<10} {'高置信度':<10} {'复合分':<10}")
    print("-"*80)

    for i, r in enumerate(results, 1):
        ts = r['timestamp'][:19] if r['timestamp'] else r['file'][:19]
        print(f"{i:<6} {ts:<20} {r['avg_std']:<10.2f} {r['high_confidence_ratio']:<10.1%} {r['composite_score']:<10.2f}")

    # 最佳结果
    print("\n" + "="*80)
    best = max(results, key=lambda x: x['composite_score'])
    print(f"最佳结果：{best['file']}")
    print(f"  平均 std: {best['avg_std']:.2f}")
    print(f"  高置信度比例: {best['high_confidence_ratio']:.1%}")
    print(f"  复合分: {best['composite_score']:.2f}")

    # 各维度详情
    print("\n各维度 std：")
    for dim_key, dim_data in best['dimensions'].items():
        print(f"  {dim_key}: {dim_data['std']:.1f}")

    # 改进趋势
    if len(results) > 1:
        print("\n" + "="*80)
        print("改进趋势：")
        first = results[0]
        last = results[-1]

        delta_std = last['avg_std'] - first['avg_std']
        delta_ratio = last['high_confidence_ratio'] - first['high_confidence_ratio']
        delta_composite = last['composite_score'] - first['composite_score']

        print(f"  平均 std: {first['avg_std']:.2f} → {last['avg_std']:.2f} ({delta_std:+.2f})")
        print(f"  高置信度比例: {first['high_confidence_ratio']:.1%} → {last['high_confidence_ratio']:.1%} ({delta_ratio:+.1%})")
        print(f"  复合分: {first['composite_score']:.2f} → {last['composite_score']:.2f} ({delta_composite:+.2f})")

        if delta_composite > 0:
            print("\n✅ 整体改进")
        elif delta_composite < 0:
            print("\n❌ 整体退步")
        else:
            print("\n⚠️ 无明显变化")

if __name__ == "__main__":
    results_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results/autoresearch/v2.56")
    analyze_results(results_dir)
