#!/usr/bin/env python3
"""
任务 3：合并评价结果

将 phase2 和 phase3 的评价结果合并到 results/fullevaluation/。
仅包含 round1-err 和 round2。
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── 路径配置 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

PHASE2_EVAL = PROJECT_ROOT / "results" / "phase2-evaluation"
PHASE3_EVAL = PROJECT_ROOT / "results" / "phase3-evaluation"
MAPPING_CACHE = PROJECT_ROOT / "results" / "merge_cache" / "pdf_mapping.json"

OUTPUT_DIR = PROJECT_ROOT / "results" / "fullevaluation"

# Phase 3 起始 ID（与 02_merge_paperlist_pdf.py 保持一致）
PHASE3_START_ID = 1837


def load_mapping() -> dict:
    """加载 PDF 映射缓存"""
    with open(MAPPING_CACHE, "r", encoding="utf-8") as f:
        return json.load(f)


def copy_round1_err():
    """原样复制 phase2 的 round1-err 目录"""
    src = PHASE2_EVAL / "round1-err"
    dst = OUTPUT_DIR / "round1-err"

    if not src.exists():
        print("   ⚠️  phase2 round1-err 目录不存在")
        return

    print(f"   复制 {src} → {dst}")
    shutil.copytree(src, dst, dirs_exist_ok=True)

    # 统计
    total = 0
    for subdir in dst.iterdir():
        if subdir.is_dir():
            count = len(list(subdir.glob("*.json")))
            print(f"     {subdir.name}: {count} 个 JSON")
            total += count
        elif subdir.suffix in (".json", ".md", ".csv", ".log"):
            total += 1

    print(f"     + 元数据文件")
    print(f"   ✅ round1-err 复制完成")


def copy_phase2_round1(mapping: dict):
    """复制 phase2 的 round1，更新 paper 路径"""
    src_dir = PHASE2_EVAL / "round1"
    dst_dir = OUTPUT_DIR / "round1"
    dst_dir.mkdir(parents=True, exist_ok=True)

    if not src_dir.exists():
        print("   ⚠️  phase2 round1 目录不存在")
        return

    count = 0
    path_updated = 0
    errors = []

    for src_file in sorted(src_dir.glob("paper-*.json")):
        dst_file = dst_dir / src_file.name

        try:
            with open(src_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            paper_id = src_file.stem.replace("paper-", "")

            if paper_id in mapping:
                new_path = mapping[paper_id].get("new_path", "")
                if new_path:
                    data["paper"] = new_path
                    path_updated += 1

            with open(dst_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            count += 1

        except Exception as e:
            errors.append({"file": src_file.name, "error": str(e)})

    print(f"   ✅ Phase 2 round1: {count} 个文件, {path_updated} 个路径已更新")
    if errors:
        print(f"   ⚠️  {len(errors)} 个文件处理失败")


def copy_phase3_round1(mapping: dict):
    """复制 phase3 的 round1，重编号 + 更新 paper 路径"""
    src_dir = PHASE3_EVAL / "round1"
    dst_dir = OUTPUT_DIR / "round1"
    dst_dir.mkdir(parents=True, exist_ok=True)

    if not src_dir.exists():
        print("   ⚠️  phase3 round1 目录不存在")
        return

    count = 0
    path_updated = 0
    errors = []

    for src_file in sorted(src_dir.glob("paper-*.json")):
        old_id_str = src_file.stem.replace("paper-", "")
        try:
            old_id = int(old_id_str)
        except ValueError:
            errors.append({"file": src_file.name, "error": "无法解析 ID"})
            continue

        new_id = PHASE3_START_ID + old_id - 1
        dst_file = dst_dir / f"paper-{new_id}.json"

        try:
            with open(src_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            new_id_str = str(new_id)
            if new_id_str in mapping:
                new_path = mapping[new_id_str].get("new_path", "")
                if new_path:
                    data["paper"] = new_path
                    path_updated += 1

            with open(dst_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            count += 1

        except Exception as e:
            errors.append({"file": src_file.name, "error": str(e)})

    print(f"   ✅ Phase 3 round1: {count} 个文件, {path_updated} 个路径已更新")
    if errors:
        print(f"   ⚠️  {len(errors)} 个文件处理失败")


def copy_phase2_round2(mapping: dict):
    """复制 phase2 的 round2，更新 paper 路径"""
    src_dir = PHASE2_EVAL / "round2"
    dst_dir = OUTPUT_DIR / "round2"
    dst_dir.mkdir(parents=True, exist_ok=True)

    if not src_dir.exists():
        print("   ⚠️  phase2 round2 目录不存在")
        return

    count = 0
    path_updated = 0
    errors = []

    for src_file in sorted(src_dir.glob("paper-*.json")):
        dst_file = dst_dir / src_file.name

        # 读取 JSON，更新 paper 路径
        try:
            with open(src_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 从文件名提取 paper ID
            paper_id = src_file.stem.replace("paper-", "")

            # 查找映射
            if paper_id in mapping:
                old_path = data.get("paper", "")
                new_path = mapping[paper_id].get("new_path", "")
                if new_path:
                    data["paper"] = new_path
                    path_updated += 1

            with open(dst_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            count += 1

        except Exception as e:
            errors.append({"file": src_file.name, "error": str(e)})

    print(f"   ✅ Phase 2 round2: {count} 个文件, {path_updated} 个路径已更新")
    if errors:
        print(f"   ⚠️  {len(errors)} 个文件处理失败")


def copy_phase3_round2(mapping: dict):
    """复制 phase3 的 round2，重编号 + 更新 paper 路径"""
    src_dir = PHASE3_EVAL / "round2"
    dst_dir = OUTPUT_DIR / "round2"
    dst_dir.mkdir(parents=True, exist_ok=True)

    if not src_dir.exists():
        print("   ⚠️  phase3 round2 目录不存在")
        return

    count = 0
    path_updated = 0
    errors = []

    for src_file in sorted(src_dir.glob("paper-*.json")):
        # 提取原始 ID
        old_id_str = src_file.stem.replace("paper-", "")
        try:
            old_id = int(old_id_str)
        except ValueError:
            errors.append({"file": src_file.name, "error": "无法解析 ID"})
            continue

        # 计算新 ID
        new_id = PHASE3_START_ID + old_id - 1
        dst_file = dst_dir / f"paper-{new_id}.json"

        try:
            with open(src_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 查找映射，更新 paper 路径
            new_id_str = str(new_id)
            if new_id_str in mapping:
                new_path = mapping[new_id_str].get("new_path", "")
                if new_path:
                    data["paper"] = new_path
                    path_updated += 1

            with open(dst_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            count += 1

        except Exception as e:
            errors.append({"file": src_file.name, "error": str(e)})

    print(f"   ✅ Phase 3 round2: {count} 个文件, {path_updated} 个路径已更新")
    if errors:
        print(f"   ⚠️  {len(errors)} 个文件处理失败")


def main():
    print("=" * 60)
    print("任务 3：合并评价结果")
    print("=" * 60)

    # 创建输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 加载映射
    print("\n📖 加载 PDF 映射...")
    mapping = load_mapping()
    print(f"   映射条目数: {len(mapping)}")

    # 1. 复制 round1-err
    print("\n📦 复制 round1-err（原样复制）...")
    copy_round1_err()

    # 2. 复制 phase2 round1
    print("\n📦 复制 phase2 round1...")
    copy_phase2_round1(mapping)

    # 3. 复制 phase3 round1（重编号）
    print("\n📦 复制 phase3 round1（重编号）...")
    copy_phase3_round1(mapping)

    # 4. 复制 phase2 round2
    print("\n📦 复制 phase2 round2...")
    copy_phase2_round2(mapping)

    # 5. 复制 phase3 round2（重编号）
    print("\n📦 复制 phase3 round2（重编号）...")
    copy_phase3_round2(mapping)

    # 6. 验证
    print(f"\n📊 验证统计:")
    round1_dir = OUTPUT_DIR / "round1"
    if round1_dir.exists():
        round1_files = list(round1_dir.glob("paper-*.json"))
        print(f"   round1 总文件数: {len(round1_files)}")

        # 检查 phase3 round1 文件
        phase3_ids = list(range(PHASE3_START_ID, PHASE3_START_ID + 90))
        found_phase3_r1 = sum(
            1 for pid in phase3_ids if (round1_dir / f"paper-{pid}.json").exists()
        )
        print(f"   Phase 3 round1 文件: {found_phase3_r1}/90")

        # 抽样检查 round1 路径
        sample_ids = [1, 100, 500, PHASE3_START_ID, PHASE3_START_ID + 89]
        print(f"\n   round1 路径抽样检查:")
        for sid in sample_ids:
            f = round1_dir / f"paper-{sid}.json"
            if f.exists():
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                paper_path = data.get("paper", "N/A")
                ok = "raw/fullpaper" in paper_path
                print(f"     paper-{sid}: {'✅' if ok else '❌'} {paper_path[:60]}...")

    round2_dir = OUTPUT_DIR / "round2"
    if round2_dir.exists():
        round2_files = list(round2_dir.glob("paper-*.json"))
        print(f"   round2 总文件数: {len(round2_files)}")

        # 检查 phase3 文件是否存在
        phase3_ids = list(range(PHASE3_START_ID, PHASE3_START_ID + 90))
        found_phase3 = sum(
            1 for pid in phase3_ids if (round2_dir / f"paper-{pid}.json").exists()
        )
        print(f"   Phase 3 round2 文件: {found_phase3}/90")

        # 抽样检查路径更新
        sample_ids = [1, 100, 500, PHASE3_START_ID, PHASE3_START_ID + 89]
        print(f"\n   路径抽样检查:")
        for sid in sample_ids:
            f = round2_dir / f"paper-{sid}.json"
            if f.exists():
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                paper_path = data.get("paper", "N/A")
                ok = "raw/fullpaper" in paper_path
                print(f"     paper-{sid}: {'✅' if ok else '❌'} {paper_path[:60]}...")

    round1_err_dir = OUTPUT_DIR / "round1-err"
    if round1_err_dir.exists():
        err_subdirs = [d for d in round1_err_dir.iterdir() if d.is_dir()]
        total_err = sum(len(list(d.glob("*.json"))) for d in err_subdirs)
        print(f"\n   round1-err: {len(err_subdirs)} 个子目录, {total_err} 个 JSON")

    print(f"\n✅ 合并完成！输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
