#!/usr/bin/env python3
"""Phase 1 样本选择脚本（30 篇版本）：从法学三大刊论文中随机抽取 30 篇"""

import random
import shutil
from pathlib import Path
import json

# 设置随机种子（可复现）
random.seed(20260518)

def select_samples_from_dir(directory: Path, count: int) -> list[Path]:
    """从目录中随机抽取指定数量的 PDF（优化版：避免全量加载）"""
    # 先获取所有 PDF 文件名（只读文件名，不创建 Path 对象）
    pdf_files = [f for f in directory.iterdir() if f.suffix == '.pdf']

    # 如果文件数不足，抛出异常
    if len(pdf_files) < count:
        raise ValueError(f"{directory} 中只有 {len(pdf_files)} 个 PDF，无法抽取 {count} 篇")

    # 随机抽取
    return random.sample(pdf_files, count)

def select_samples_from_three_journals():
    """从三大刊随机抽取 30 篇样本"""
    samples = []

    # 中国法学：12 篇
    faxue_dir = Path("法学三大刊论文/中国法学")
    samples.extend(select_samples_from_dir(faxue_dir, 12))

    # 法学研究：12 篇
    yanjiu_dir = Path("法学三大刊论文/法学研究")
    samples.extend(select_samples_from_dir(yanjiu_dir, 12))

    # 中国社会科学：6 篇
    shehui_dir = Path("法学三大刊论文/中国社会科学")
    samples.extend(select_samples_from_dir(shehui_dir, 6))

    return samples

def copy_samples_to_phase1(samples):
    """复制样本到 raw/phase1-30-papers/"""
    output_dir = Path("raw/phase1-30-papers")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 复制样本
    for i, sample in enumerate(samples, 1):
        shutil.copy(sample, output_dir / f"{i:02d}_{sample.name}")

    # 生成样本清单
    manifest = {
        "samples": [str(s) for s in samples],
        "total": len(samples),
        "seed": 20260518,
        "source": "三大刊（中国法学 12 + 法学研究 12 + 中国社会科学 6）",
        "note": "不预设好/差标签，随机抽取"
    }

    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"✅ 样本已复制到 {output_dir}")
    print(f"   总数：{len(samples)} 篇")
    print(f"   - 中国法学：12 篇")
    print(f"   - 法学研究：12 篇")
    print(f"   - 中国社会科学：6 篇")
    print(f"\n样本清单：{output_dir / 'manifest.json'}")

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 1 样本选择（30 篇版本）")
    print("=" * 60)
    print("从法学三大刊论文中随机抽取 30 篇样本")
    print("  - 中国法学：12 篇")
    print("  - 法学研究：12 篇")
    print("  - 中国社会科学：6 篇")
    print("  - 随机种子：20260518（可复现）")
    print("  - 不预设好/差标签")
    print("=" * 60 + "\n")

    samples = select_samples_from_three_journals()
    copy_samples_to_phase1(samples)

    print("\n✅ 样本选择完成！")
    print("\n下一步：运行 Phase 1 测试")
    print("  .venv/bin/python scripts/phase1_30_papers_test.py")
