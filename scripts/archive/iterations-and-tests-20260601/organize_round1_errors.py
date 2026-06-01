#!/usr/bin/env python3
"""
整理 Phase 2 Round 1 评审结果：分类有问题的论文

将有问题的论文复制到 round1-err/ 目录下的分类子目录中：
1. 1-empty-status/: 空状态论文（至少 1 个模型返回空结果）
2. 2-all-reject/: 4 个模型全部拒绝
3. 3-majority-reject/: 2-3 个模型拒绝
4. 4-single-reject/: 1 个模型拒绝
5. 5-boundary-only/: 仅边界判断（无拒绝）

优先级：空状态 > 全部拒绝 > 多数拒绝 > 单个拒绝 > 仅边界
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict


def load_result(file_path: Path) -> Dict[str, Any]:
    """加载单个评审结果文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def classify_paper(paper_data: Dict[str, Any], paper_id: str) -> Tuple[str, Dict[str, Any]]:
    """
    分类论文

    返回：(分类类别, 分类详情)
    """
    precheck = paper_data.get('precheck', {})

    # 统计各模型的状态
    empty_models = []
    reject_models = []
    boundary_models = []
    pass_models = []

    for model, data in precheck.items():
        if not isinstance(data, dict):
            continue

        status = data.get('status', '')
        conclusion = data.get('conclusion', '')

        # 检查空状态
        if status == '' and conclusion == '':
            empty_models.append(model)
        # 检查拒绝
        elif conclusion == 'obviously_ineligible':
            reject_models.append(model)
        # 检查边界
        elif conclusion == 'boundary_review':
            boundary_models.append(model)
        # 检查通过
        elif conclusion == 'enter_six_dimension_review':
            pass_models.append(model)

    # 按优先级分类
    details = {
        'paper_id': paper_id,
        'paper_name': paper_data.get('paper', 'unknown'),
        'empty_models': empty_models,
        'reject_models': reject_models,
        'boundary_models': boundary_models,
        'pass_models': pass_models,
        'empty_count': len(empty_models),
        'reject_count': len(reject_models),
        'boundary_count': len(boundary_models),
        'pass_count': len(pass_models)
    }

    # 优先级 1: 空状态
    if empty_models:
        return '1-empty-status', details

    # 优先级 2: 4 个模型全部拒绝
    if len(reject_models) == 4:
        return '2-all-reject', details

    # 优先级 3: 2-3 个模型拒绝
    if len(reject_models) >= 2:
        return '3-majority-reject', details

    # 优先级 4: 1 个模型拒绝
    if len(reject_models) == 1:
        return '4-single-reject', details

    # 优先级 5: 仅边界判断（无拒绝）
    if boundary_models and not reject_models:
        return '5-boundary-only', details

    # 不属于任何问题类别
    return None, details


def copy_to_category(src_path: Path, category: str, base_dir: Path) -> Path:
    """复制文件到分类目录"""
    target_dir = base_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / src_path.name
    shutil.copy2(src_path, target_path)

    return target_path


def generate_summary(classified_papers: Dict[str, List[Dict]], base_dir: Path):
    """生成错误汇总报告"""
    # 统计各类别数量
    summary = {
        'total': sum(len(papers) for papers in classified_papers.values()),
        '1-empty-status': len(classified_papers.get('1-empty-status', [])),
        '2-all-reject': len(classified_papers.get('2-all-reject', [])),
        '3-majority-reject': len(classified_papers.get('3-majority-reject', [])),
        '4-single-reject': len(classified_papers.get('4-single-reject', [])),
        '5-boundary-only': len(classified_papers.get('5-boundary-only', []))
    }

    # 统计空状态模型
    empty_status_models = defaultdict(int)
    for paper in classified_papers.get('1-empty-status', []):
        for model in paper['empty_models']:
            empty_status_models[model] += 1

    # 统计拒绝模型
    reject_models = defaultdict(int)
    for category in ['2-all-reject', '3-majority-reject', '4-single-reject']:
        for paper in classified_papers.get(category, []):
            for model in paper['reject_models']:
                reject_models[model] += 1

    # 统计边界模型
    boundary_models = defaultdict(int)
    for category in ['5-boundary-only']:
        for paper in classified_papers.get(category, []):
            for model in paper['boundary_models']:
                boundary_models[model] += 1

    # 生成报告
    report = {
        'summary': summary,
        'empty_status_models': dict(sorted(empty_status_models.items(), key=lambda x: x[1], reverse=True)),
        'reject_models': dict(sorted(reject_models.items(), key=lambda x: x[1], reverse=True)),
        'boundary_models': dict(sorted(boundary_models.items(), key=lambda x: x[1], reverse=True)),
        'papers': classified_papers
    }

    # 保存报告
    output_file = base_dir / 'error-summary.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return output_file


def generate_readme(summary_data: Dict, base_dir: Path):
    """生成说明文档"""
    summary = summary_data['summary']

    readme_content = f"""# Phase 2 Round 1 评审问题论文分类

本目录包含 Phase 2 Round 1 评审中有问题的论文，共 **{summary['total']} 篇**。

## 目录结构

```
round1-err/
├── 1-empty-status/        # 空状态论文（{summary['1-empty-status']} 篇）
├── 2-all-reject/          # 4 个模型全部拒绝（{summary['2-all-reject']} 篇）
├── 3-majority-reject/     # 2-3 个模型拒绝（{summary['3-majority-reject']} 篇）
├── 4-single-reject/       # 1 个模型拒绝（{summary['4-single-reject']} 篇）
├── 5-boundary-only/       # 仅边界判断（{summary['5-boundary-only']} 篇）
├── error-summary.json     # 错误汇总报告
└── README.md              # 本文档
```

## 分类规则

论文按以下优先级分类（一个论文只归入一个目录）：

1. **1-empty-status/**：至少 1 个模型返回空状态（空 `status` 和空 `conclusion`）
   - 原因：API 调用失败、超时、内容审查等
   - 处理：需要补测空状态模型

2. **2-all-reject/**：4 个模型全部判定为 `obviously_ineligible`
   - 原因：论文明显不符合项目口径（政策性论文、宣传性论文等）
   - 处理：可直接排除，不进入后续评审

3. **3-majority-reject/**：2-3 个模型判定为 `obviously_ineligible`
   - 原因：多数模型认为不符合项目口径，但有分歧
   - 处理：需要人工复核，决定是否进入六维评审

4. **4-single-reject/**：1 个模型判定为 `obviously_ineligible`
   - 原因：少数模型认为不符合项目口径
   - 处理：需要人工复核，决定是否进入六维评审

5. **5-boundary-only/**：至少 1 个模型判定为 `boundary_review`，但无拒绝
   - 原因：论文处于项目口径边界，需要人工判断
   - 处理：需要人工确认是否进入六维评审

## 模型统计

### 空状态模型分布
"""

    # 添加空状态模型统计
    for model, count in summary_data['empty_status_models'].items():
        readme_content += f"- **{model}**: {count} 篇\n"

    readme_content += "\n### 拒绝模型分布\n"

    # 添加拒绝模型统计
    for model, count in summary_data['reject_models'].items():
        readme_content += f"- **{model}**: {count} 篇\n"

    readme_content += """
## 后续处理建议

1. **1-empty-status/**：
   - 运行补测脚本，重新评审空状态模型
   - 补测完成后，重新分类（可能进入其他类别或成功通过）

2. **2-all-reject/**：
   - 直接排除，不进入后续评审
   - 这些论文 4 个模型达成一致，无争议

3. **3-majority-reject/** + **4-single-reject/**：
   - 人工复核，决定是否进入六维评审
   - 重点关注模型分歧的原因

4. **5-boundary-only/**：
   - 人工确认，决定是否进入六维评审
   - 这些论文处于项目口径边界

5. **round1/** 中的成功论文：
   - 继续 Round 2 交叉评审

## 使用方式

查看详细统计信息：
```bash
cat error-summary.json | jq '.summary'
```

查看某个类别的论文列表：
```bash
cat error-summary.json | jq '.papers["1-empty-status"]'
```

查看空状态模型统计：
```bash
cat error-summary.json | jq '.empty_status_models'
```

查看拒绝模型统计：
```bash
cat error-summary.json | jq '.reject_models'
```
"""

    # 保存 README
    readme_file = base_dir / 'README.md'
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write(readme_content)

    return readme_file


def main():
    """主函数"""
    # 设置路径
    project_root = Path(__file__).parent.parent
    round1_dir = project_root / 'results' / 'phase2-evaluation' / 'round1'
    round1_err_dir = project_root / 'results' / 'phase2-evaluation' / 'round1-err'

    if not round1_dir.exists():
        print(f"错误: 源目录不存在: {round1_dir}")
        return

    # 创建目标目录
    round1_err_dir.mkdir(parents=True, exist_ok=True)

    # 分类结果
    classified_papers = {
        '1-empty-status': [],
        '2-all-reject': [],
        '3-majority-reject': [],
        '4-single-reject': [],
        '5-boundary-only': []
    }

    # 统计
    total_files = 0
    classified_count = 0
    skipped_count = 0

    print("=" * 80)
    print("开始分类 Phase 2 Round 1 评审结果")
    print("=" * 80)
    print()

    # 遍历所有 paper-*.json 文件
    paper_files = sorted(round1_dir.glob('paper-*.json'))
    total_files = len(paper_files)

    print(f"找到 {total_files} 个论文文件")
    print()

    for file_path in paper_files:
        paper_id = file_path.stem

        try:
            # 加载论文数据
            paper_data = load_result(file_path)

            # 分类
            category, details = classify_paper(paper_data, paper_id)

            if category:
                # 复制到分类目录
                target_path = copy_to_category(file_path, category, round1_err_dir)

                # 记录分类结果
                classified_papers[category].append(details)
                classified_count += 1

                # 输出日志
                print(f"✓ {paper_id} → {category}")
                print(f"  空状态: {details['empty_count']}, 拒绝: {details['reject_count']}, "
                      f"边界: {details['boundary_count']}, 通过: {details['pass_count']}")
            else:
                skipped_count += 1

        except Exception as e:
            print(f"✗ {paper_id}: 处理失败 - {e}")
            skipped_count += 1

    print()
    print("=" * 80)
    print("分类完成")
    print("=" * 80)
    print()
    print(f"总文件数: {total_files}")
    print(f"已分类: {classified_count}")
    print(f"跳过: {skipped_count}")
    print()

    # 输出各类别统计
    print("各类别统计:")
    for category in ['1-empty-status', '2-all-reject', '3-majority-reject', '4-single-reject', '5-boundary-only']:
        count = len(classified_papers[category])
        print(f"  {category}: {count} 篇")
    print()

    # 生成汇总报告
    print("生成汇总报告...")
    summary_file = generate_summary(classified_papers, round1_err_dir)
    print(f"✓ 汇总报告: {summary_file}")

    # 生成 README
    print("生成说明文档...")
    with open(summary_file, 'r', encoding='utf-8') as f:
        summary_data = json.load(f)
    readme_file = generate_readme(summary_data, round1_err_dir)
    print(f"✓ 说明文档: {readme_file}")

    print()
    print("=" * 80)
    print("全部完成！")
    print("=" * 80)
    print()
    print(f"结果目录: {round1_err_dir}")
    print()
    print("验证命令:")
    print(f"  ls {round1_err_dir}/*/paper-*.json | wc -l  # 应为 {classified_count}")
    print(f"  cat {summary_file} | jq '.summary'")


if __name__ == '__main__':
    main()
