#!/usr/bin/env python3
"""把历史制品复制到仓库同级冷归档，校验 SHA-256 后删除源文件。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

DEFAULT_PATHS = (
    "results/archive",
    "scripts/archive",
    "logs",
    ".firecrawl",
    "research",
    ".plan",
    ".claude/skills/autoresearch",
    ".baoyu-skills/baoyu-image-gen/EXTEND.md",
    "update_editor.sql",
    "projects",
    "docs/presentations/full-render",
    "docs/presentations/p1-p6-p18-render",
    "docs/presentations/preview-3p-render",
)
GLOBS = (
    "docs/presentations/*.pptx",
    "docs/presentations/*.pdf",
    "docs/reports/*.pdf",
    "slide-deck/**/*.pptx",
    "slide-deck/**/*.pdf",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collect(source_root: Path, extra_paths: tuple[str, ...] = ()) -> list[Path]:
    paths: set[Path] = set()
    for relative in (*DEFAULT_PATHS, *extra_paths):
        path = source_root / relative
        if path.is_file():
            paths.add(path)
        elif path.is_dir():
            paths.update(item for item in path.rglob("*") if item.is_file())
    for pattern in GLOBS:
        paths.update(item for item in source_root.glob(pattern) if item.is_file())
    return sorted(paths)


def archive(
    source_root: Path,
    archive_root: Path,
    execute: bool,
    extra_paths: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    files = collect(source_root, extra_paths)
    for source in files:
        relative = source.relative_to(source_root)
        target = archive_root / relative
        record: dict[str, object] = {
            "original_path": str(relative),
            "archive_path": str(target),
            "bytes": source.stat().st_size,
            "sha256": sha256(source),
            "reason": "历史制品或本地运行产物；源码优先，迁入冷归档",
            "status": "planned",
        }
        if execute:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if target.stat().st_size != record["bytes"] or sha256(target) != record["sha256"]:
                raise RuntimeError(f"归档校验失败: {relative}")
            source.unlink()
            record["status"] = "verified-and-removed"
        records.append(record)

    if execute:
        for directory in sorted(
            {path.parent for path in files}, key=lambda item: len(item.parts), reverse=True
        ):
            if directory != source_root:
                try:
                    directory.rmdir()
                except OSError:
                    pass
        archive_root.mkdir(parents=True, exist_ok=True)
        manifest = archive_root / "manifest.jsonl"
        with manifest.open("a", encoding="utf-8") as handle:
            handle.write(
                "".join(
                    json.dumps(record, ensure_ascii=False) + "\n"
                    for record in records
                )
            )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path("."))
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=Path("../SocialEval-archive") / f"{date.today()}-deep-clean",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--path", action="append", default=[])
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    records = archive(
        args.source_root.resolve(),
        args.archive_root.resolve(),
        args.execute,
        tuple(args.path),
    )
    total = sum(int(record["bytes"]) for record in records)
    print(f"files={len(records)} bytes={total} execute={args.execute}")
