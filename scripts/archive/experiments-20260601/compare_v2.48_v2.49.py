#!/usr/bin/env python3
"""对比 v2.48 和 v2.49 的测试结果"""

import json
from pathlib import Path
from typing import Dict, List

def load_result(path: Path) -> Dict:
    """加载测试结果"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_triggered_rules(result: Dict) -> List[Dict]:
    """提取触发的规则"""
    rules = []
    for dim_key, dim_data in result.get('dimensions', {}).items():
        for model in ['qwen3.6-plus', 'glm-5.1']:
            raw = dim_data.get('raw_outputs', ).get(model, {})
            triggered = raw.get('limit_rule_triggered', [])
            for rule in triggered:
                rules.append({
                    'dimension': dim_key,
                    'model': model,
                    'rule_id': rule.get('rule_id'),
                    'score_ceiling': rule.get('score_ceiling'),
                    'evidence': rule.get('evidence', '')[:100]
                })
    return rules

def compare_results(v248_path: Path, v249_path: Path, paper_name: str):
    """对比两个版本的结果"""
    print(f"\n{'='*80}")
    print(f"论文：{paper_name}")
    print(f"{'='*80}\n")

    # 加载结果
    v248 = load_result(v248_path) if v248_path.exists() else None
    v249 = load_result(v249_path)

    # 对比总分
    print("## 总分对比\n")
    if v248:
        v248_score = v248.get('overall', {}).get('weighted_total', 0)
        print(f"v2.48: {v248_score:.1f}")
    v249_score = v249.get('overall', {}).get('weighted_total', 0)
    print(f"v2.49: {v249_score:.1f}")
    if v248:
        delta = v249_score - v248_score
        print(f"变化: {delta:+.1f} ({'降低' if delta < 0 else '升高'})")

    # 对比维度得分
    print("\n## 维度得分对比\n")
    print(f"{'维度':<20} {'v2.48':<10} {'v2.49':<10} {'变化':<10}")
    print("-" * 60)

    for dim_key in ['problem_originality', 'analytical_framework', 'conclusion_consensus']:
        if v248:
            v248_dim = v248.get('dimensions', {}).get(dim_key, {}).get('mean', 0)
        else:
            v248_dim = 0
        v249_dim = v249.get('dimensions', {}).get(dim_key, {}).get('mean', 0)
        delta = v249_dim - v248_dim if v248 else 0

        dim_name = {
            'problem_originality': '问题创新性',
            'analytical_framework': '分析框架',
            'conclusion_consensus': '结论可接受性'
        }.get(dim_key, dim_key)

        if v248:
            print(f"{dim_name:<20} {v248_dim:<10.1f} {v249_dim:<10.1f} {delta:+.1f}")
        else:
            print(f"{dim_name:<20} {'N/A':<10} {v249_dim:<10.1f} {'N/A':<10}")

    # 对比触发规则
    print("\n## 触发规则对比\n")

    if v248:
        v248_rules = extract_triggered_rules(v248)
        print(f"v2.48 触发规则数: {len(v248_rules)}")
        for rule in v248_rules:
            print(f"  - {rule['rule_id']} (上限 {rule['score_ceiling']})")

    v249_rules = extract_triggered_rules(v249)
    print(f"\nv2.49 触发规则数: {len(v249_rules)}")
    for rule in v249_rules:
        print(f"  - {rule['rule_id']} (上限 {rule['score_ceiling']})")
        if rule['evidence']:
            print(f"    证据: {rule['evidence']}...")

    # 新增规则触发情况
    new_rules = [
        'new_term_old_problem',
        'slogan_advocacy',
        'concept_stacking',
        'theory_practice_gap',
        'mechanical_application',
        'insufficient_support'
    ]

    triggered_new = [r for r in v249_rules if any(nr in r['rule_id'] for nr in new_rules)]
    print(f"\n新增规则触发数: {len(triggered_new)}/{len(new_rules)}")
    if triggered_new:
        print("触发的新规则:")
        for rule in triggered_new:
            print(f"  ✅ {rule['rule_id']} (上限 {rule['score_ceiling']})")
    else:
        print("  ❌ 无新规则触发")

def main():
    """主函数"""
    # 定义测试对
    tests = [
        {
            'name': '陈姿君',
            'v248': None,  # v2.48 结果路径（如果有）
            'v249': Path('results/v2.49-test/verify-chenzijun.json')
        },
        {
            'name': '曹俊金',
            'v248': None,  # v2.48 结果路径（如果有）
            'v249': Path('results/v2.49-test/verify-caojunjin.json')
        }
    ]

    for test in tests:
        if test['v249'].exists():
            compare_results(test['v248'], test['v249'], test['name'])
        else:
            print(f"\n⏳ {test['name']}: 测试尚未完成")

    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    main()
