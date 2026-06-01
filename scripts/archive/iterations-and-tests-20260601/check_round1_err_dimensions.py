#!/usr/bin/env python3
"""检查 round1-err 中 2-6 类论文的六维评价完整性"""

import json
from pathlib import Path
from collections import defaultdict

# 六维度标准名称
EXPECTED_DIMENSIONS = {
    "research_innovation",
    "current_insight",
    "theoretical_construction",
    "logical_coherence",
    "academic_consensus",
    "forward_extension"
}

def check_paper_dimensions(paper_path: Path) -> dict:
    """检查单篇论文的维度完整性"""
    with open(paper_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    result = {
        "paper_id": data.get("paper_id", paper_path.stem),
        "paper_path": str(paper_path),
        "models": {}
    }

    # 获取模型列表
    model_names = data.get("models", [])
    if isinstance(model_names, list):
        # models 是数组，需要从 precheck 和 dimensions 中提取数据
        for model_name in model_names:
            dimensions = set()

            # 从 dimensions 字段中提取
            if "dimensions" in data and model_name in data["dimensions"]:
                dimensions = set(data["dimensions"][model_name].keys())

            # 从 precheck 中获取状态
            status = None
            conclusion = None
            if "precheck" in data and model_name in data["precheck"]:
                precheck = data["precheck"][model_name]
                status = precheck.get("status")
                conclusion = precheck.get("conclusion")

            result["models"][model_name] = {
                "has_dimensions": len(dimensions) > 0,
                "dimension_count": len(dimensions),
                "dimensions": sorted(dimensions),
                "missing": sorted(EXPECTED_DIMENSIONS - dimensions),
                "status": status,
                "conclusion": conclusion
            }
    else:
        # 旧格式：models 是字典
        for model_name, model_data in data.get("models", {}).items():
            dimensions = set()

            # 检查 dimensions 字段
            if "dimensions" in model_data and model_data["dimensions"]:
                dimensions = set(model_data["dimensions"].keys())

            result["models"][model_name] = {
                "has_dimensions": len(dimensions) > 0,
                "dimension_count": len(dimensions),
                "dimensions": sorted(dimensions),
                "missing": sorted(EXPECTED_DIMENSIONS - dimensions),
                "status": model_data.get("status"),
                "conclusion": model_data.get("conclusion")
            }

    return result

def main():
    base_dir = Path("results/phase2-evaluation/round1-err")

    # 要检查的目录
    categories = [
        "2-all-reject",
        "3-majority-reject",
        "4-single-reject",
        "5-boundary-only"
    ]

    all_results = {}
    summary = defaultdict(lambda: {
        "total_papers": 0,
        "papers_with_missing_dims": 0,
        "models_with_missing_dims": defaultdict(int),
        "papers": []
    })

    for category in categories:
        cat_dir = base_dir / category
        if not cat_dir.exists():
            print(f"⚠️  目录不存在: {category}")
            continue

        print(f"\n{'='*60}")
        print(f"检查 {category}")
        print(f"{'='*60}")

        json_files = sorted(cat_dir.glob("paper-*.json"))
        print(f"找到 {len(json_files)} 篇论文\n")

        for paper_path in json_files:
            result = check_paper_dimensions(paper_path)
            paper_id = result["paper_id"]

            summary[category]["total_papers"] += 1

            # 输出每篇论文的详细信息
            print(f"📄 {paper_id}:")

            # 检查是否有模型缺失维度
            has_missing = False
            for model_name, model_info in result["models"].items():
                status = model_info.get("status")
                conclusion = model_info.get("conclusion", "unknown")

                # 判断是否应该有六维评价
                should_have_dimensions = (
                    status == "pass" and conclusion == "enter_six_dimension_review"
                )

                if should_have_dimensions:
                    # 应该有六维评价
                    if len(model_info["missing"]) > 0:
                        has_missing = True
                        summary[category]["models_with_missing_dims"][model_name] += 1
                        print(f"  ❌ {model_name}: 应有六维但缺失 {len(model_info['missing'])} 个 - {model_info['missing']}")
                    else:
                        print(f"  ✅ {model_name}: 六维完整 ({model_info['dimension_count']}/6)")
                else:
                    # 不应该有六维评价
                    if model_info["dimension_count"] > 0:
                        print(f"  ⚠️  {model_name}: {conclusion} 但有 {model_info['dimension_count']} 个维度（异常）")
                    else:
                        print(f"  ⏭️ {model_name}: {conclusion} (无需六维评价)")

            if has_missing:
                summary[category]["papers_with_missing_dims"] += 1
                summary[category]["papers"].append({
                    "paper_id": paper_id,
                    "paper_path": str(paper_path),
                    "models": result["models"]
                })

            print()  # 空行分隔

    # 输出汇总报告
    print(f"\n{'='*60}")
    print("汇总报告")
    print(f"{'='*60}")

    for category in categories:
        cat_summary = summary[category]
        print(f"\n{category}:")
        print(f"  总论文数: {cat_summary['total_papers']}")
        print(f"  有缺失维度的论文数: {cat_summary['papers_with_missing_dims']}")

        if cat_summary['models_with_missing_dims']:
            print(f"  模型缺失维度统计:")
            for model, count in sorted(cat_summary['models_with_missing_dims'].items()):
                print(f"    - {model}: {count} 篇")

    # 保存详细报告
    output_path = base_dir / "dimension-check-report.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(dict(summary), f, indent=2, ensure_ascii=False)

    print(f"\n详细报告已保存到: {output_path}")

if __name__ == "__main__":
    main()
