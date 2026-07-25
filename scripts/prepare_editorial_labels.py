#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
from pathlib import Path

import yaml

from src.editorial.label_evaluation import load_label_manifest

REVIEW_MARKERS = ("意见", "评阅", "审稿")


def _record(
    identifier: str,
    journal: str,
    manuscript: Path,
    review: Path,
) -> dict:
    return {
        "id": identifier,
        "journal": journal,
        "manuscript_path": str(manuscript),
        "review_path": str(review),
        "human_decision": "",
        "human_issues": [],
        "label_status": "待编辑盲标",
    }


def build_blind_template(label_root: Path) -> list[dict]:
    """只按明确的目录/序号配对，不从文件名中的决定词推断标签。"""

    records: list[dict] = []
    jiaoda_root = label_root / "交大法学审稿意见"
    for index, directory in enumerate(
        sorted(path for path in jiaoda_root.iterdir() if path.is_dir()),
        start=1,
    ):
        files = sorted(
            path
            for path in directory.iterdir()
            if path.is_file() and path.name != ".DS_Store"
        )
        reviews = [
            path
            for path in files
            if any(marker in path.name for marker in REVIEW_MARKERS)
        ]
        manuscripts = [path for path in files if path not in reviews]
        if len(reviews) != 1 or len(manuscripts) != 1:
            raise ValueError(f"无法唯一配对目录：{directory}")
        records.append(
            _record(f"JDFX-{index:02d}", "交大法学", manuscripts[0], reviews[0])
        )

    academic_root = label_root / "学术月刊审稿意见"
    groups: dict[str, list[Path]] = {}
    for path in academic_root.iterdir():
        if path.is_file() and path.name != ".DS_Store":
            groups.setdefault(path.name.split("-", 1)[0], []).append(path)
    for index, key in enumerate(sorted(groups, key=int), start=1):
        files = sorted(groups[key])
        reviews = [path for path in files if "-2" in path.name]
        manuscripts = [path for path in files if "-1" in path.name]
        if len(reviews) != 1 or len(manuscripts) != 1:
            raise ValueError(f"无法唯一配对学术月刊样本组：{key}")
        records.append(
            _record(f"XSYK-{index:02d}", "学术月刊", manuscripts[0], reviews[0])
        )
    if len(records) != 12:
        raise ValueError(f"预期 12 组双期刊样本，实际找到 {len(records)} 组")
    return records


def write_blind_template(label_root: Path, destination: Path) -> None:
    records = build_blind_template(label_root)
    path_digest = hashlib.sha256(
        "\n".join(
            f"{record['id']}|{record['manuscript_path']}|{record['review_path']}"
            for record in records
        ).encode()
    ).hexdigest()
    payload = {
        "schema_version": 1,
        "purpose": "双期刊编辑盲校准",
        "instructions": [
            "先仅阅读匿名稿并填写 human_decision 与 human_issues。",
            "完成并锁定盲标后，才能打开历史审稿意见核对。",
            "不得根据文件名中的决定词填写标签。",
        ],
        "path_manifest_sha256": path_digest,
        "records": records,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def convert_legacy_doc(source: Path, output_dir: Path) -> Path:
    """用本地 LibreOffice 派生 DOCX，保留原始 DOC。"""

    if source.suffix.lower() != ".doc":
        return source
    executable = shutil.which("soffice")
    if executable is None:
        raise RuntimeError("soffice is required to convert legacy .doc files")
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{source.stem}.docx"
    if destination.exists():
        return destination
    subprocess.run(
        [
            executable,
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(output_dir),
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    if not destination.exists():
        raise RuntimeError(f"LibreOffice did not create {destination}")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a human-confirmed label manifest and derive DOCX files."
    )
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument(
        "--initialize",
        action="store_true",
        help="从 raw/label 生成不含人工决定的 12 组盲标模板",
    )
    parser.add_argument("--label-root", type=Path, default=Path("raw/label"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("raw/label-derived/editorial-blind-manifest.yaml"),
    )
    parser.add_argument(
        "--derived-dir",
        type=Path,
        default=Path("raw/label-derived/docx"),
    )
    args = parser.parse_args()
    if args.initialize:
        write_blind_template(args.label_root, args.output)
        print(f"initialized=12 output={args.output}")
        return
    if args.manifest is None:
        parser.error("必须提供 manifest，或使用 --initialize")
    records = load_label_manifest(args.manifest)
    converted = 0
    for record in records:
        for field in ("manuscript_path", "review_path"):
            source = Path(str(record.get(field, "")))
            if source.suffix.lower() == ".doc":
                convert_legacy_doc(source, args.derived_dir / record["id"])
                converted += 1
    print(f"validated={len(records)} converted={converted}")


if __name__ == "__main__":
    main()
