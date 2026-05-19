#!/usr/bin/env python3
"""Phase 1 样本选择脚本：从法学三大刊论文中随机抽取 100 篇"""

import random
import shutil
from pathlib import Path
import json

# 设置随机种子（可复现）
random.seed(20260518)

def select_samples_from_three_journals():
    """从三大刊随机抽取 100 篇样本"""
    samples = []

    # 中国法学：40 篇
    faxue_dir = Path("法学三大刊论文/中国法学")
    faxue_pdfs = list(faxue_dir.glob("*.pdf"))
    samples.extend(random.sample(faxue_pdfs, 40))

    # 法学研究：40 篇
    yanjiu_dir = Path("法学三大刊论文/法学研究")
    yanjiu_pdfs = list(yanjiu_dir.glob("*.pdf"))
    samples.extend(random.sample(yanjiu_pdfs, 40))

    # 中国社会科学：20 篇
    shehui_dir = Path("法学三大刊论文/中国社会科学")
    shehui_pdfs = list(shehui_dir.glob("*.pdf"))
    samples.extend(random.sample(shehui_pdfs, 20))

    return samples

def copy_samples_to_phase1(samples):
    """复制样本到 raw/phase1-100-papers/"""
    output_dir = Path("raw/phase1-100-papers")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 复制样本
    for i, sample in enumerate(samples, 1):
        shutil.copy(sample, output_dir / f"{i:03d}_{sample.name}")

    # 生成样本清单
    manifest = {
        "samples": [str(s) for s in samples],
        "total": len(samples),
        "seed": 20260518,
        "source": "三大刊（中国法学 40 + 法学研究 40 + 中国社会科学 20）",
        "note": "不预设好/差标签，随机抽取"
    }

    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"✅ 样本已复制到 {output_dir}")
    print(f"   总数：{len(samples)} 篇")
    print(f"   - 中国法学：40 篇")
    print(f"   - 法学研究：40 篇")
    print(f"   - 中国社会科学：20 篇")
    print(f"\n样本清单：{output_dir / 'manifest.json'}")

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 1 样本选择")
    print("=" * 60)
    print("从法学三大刊论文中随机抽取 100 篇样本")
    print("  - 中国法学：40 篇")
    print("  - 法学研究：40 篇")
    print("  - 中国社会科学：20 篇")
    print("  - 随机种子：20260518（可复现）")
    print("  - 不预设好/差标签")
    print("=" * 60 + "\n")

    samples = select_samples_from_three_journals()
    copy_samples_to_phase1(samples)

    print("\n✅ 样本选择完成！")
    print("\n下一步：运行 Phase 1 测试")
    print("  python scripts/phase1_100_papers_test.py")
