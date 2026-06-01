#!/usr/bin/env python3
"""
对比 v2.55 和 v2.56 的测试结果
"""
import json
import statistics
from pathlib import Path

# 路径配置
PROJECT_ROOT = Path(__file__).parent.parent
V255_DIR = PROJECT_ROOT / "results" / "phase2-test-10" / "round1"
V256_DIR = PROJECT_ROOT / "results" / "v2.56-test-5-papers"

# 测试的 5 篇论文
PAPER_IDS = [8, 4, 1, 10, 6]

def load_v255_results():
    """加载 v2.55 的结果（Phase 2 Round 1）"""
    results = {}
    for paper_id in PAPER_IDS:
        paper_file = V255_DIR / f"paper-{paper_id}.json"
        with open(paper_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 提取各维度的 std（直接从 dimensions 中读取）
        dimensions_data = data.get('dimensions', {})
        dim_stds = [dim_data.get('std', 0) for dim_data in dimensions_data.values()]
        max_std = max(dim_stds) if dim_stds else 0

        # 保存维度数据（用于后续分析）
        dimensions = {k: v.get('model_scores', {}) for k, v in dimensions_data.items()}

        results[paper_id] = {
            'max_std': max_std,
            'dimensions': dimensions
        }

    return results

def load_v256_results():
    """加载 v2.56 的结果"""
    # 找到最新的结果文件
    result_files = list(V256_DIR.glob("raw_results_*.json"))
    if not result_files:
        raise FileNotFoundError("未找到 v2.56 测试结果")

    latest_file = max(result_files, key=lambda p: p.stat().st_mtime)

    with open(latest_file, 'r', encoding='utf-8') as f:
        raw_results = json.load(f)

    # 新格式：每个元素是 {paper_id, dimension_results}
    results = {}
    for paper_result in raw_results:
        paper_id = paper_result['paper_id']
        dimension_results = paper_result['dimension_results']

        # 提取各维度的 std
        dim_stds = [dim_data['std'] for dim_data in dimension_results.values()]
        max_std = max(dim_stds) if dim_stds else 0

        # 提取各维度的分数（用于后续分析）
        dimensions = {}
        for dim_key, dim_data in dimension_results.items():
            dimensions[dim_key] = dim_data.get('model_scores', {})

        results[paper_id] = {
            'max_std': max_std,
            'dimensions': dimensions
        }

    return results

def main():
    print("="*70)
    print("v2.55 vs v2.56 对比分析")
    print("="*70)

    v255_results = load_v255_results()
    v256_results = load_v256_results()

    print(f"\n{'Paper ID':<10} {'v2.55 std':<12} {'v2.56 std':<12} {'变化':<10} {'改善':<8}")
    print("-" * 70)

    v255_stds = []
    v256_stds = []
    improvements = []

    for paper_id in PAPER_IDS:
        v255_std = v255_results[paper_id]['max_std']
        v256_std = v256_results.get(paper_id, {}).get('max_std', 0)

        change = v256_std - v255_std
        improvement = "✅" if change < 0 else "❌"

        v255_stds.append(v255_std)
        v256_stds.append(v256_std)
        improvements.append(change)

        print(f"{paper_id:<10} {v255_std:<12.1f} {v256_std:<12.1f} {change:<10.1f} {improvement:<8}")

    print("-" * 70)

    avg_v255 = statistics.mean(v255_stds)
    avg_v256 = statistics.mean(v256_stds)
    avg_improvement = statistics.mean(improvements)

    print(f"{'平均':<10} {avg_v255:<12.1f} {avg_v256:<12.1f} {avg_improvement:<10.1f}")

    print("\n" + "="*70)
    print("总结")
    print("="*70)
    print(f"v2.55 平均 std: {avg_v255:.2f}")
    print(f"v2.56 平均 std: {avg_v256:.2f}")
    if avg_v255 > 0:
        print(f"平均改善: {avg_improvement:.2f} ({avg_improvement/avg_v255*100:.1f}%)")
    else:
        print(f"平均改善: {avg_improvement:.2f}")

    improved_count = sum(1 for c in improvements if c < 0)
    print(f"改善论文数: {improved_count}/{len(PAPER_IDS)}")

    # 判断效果
    print("\n" + "="*70)
    if avg_v256 < 20:
        print("✅ 效果显著：命名不一致是主要问题，修复有效")
    elif avg_v256 < 25:
        print("⚠️ 有改善但不够显著：可能需要进一步调整 prompt 内容")
    else:
        print("❌ 改善不明显：需要更深入的 prompt 优化（考虑 autoresearch）")
    print("="*70)

if __name__ == "__main__":
    main()
