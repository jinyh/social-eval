#!/usr/bin/env python3
"""生成当前框架—代码—结果对应关系审计报告。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.integrity import audit_active_results  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/reports/current/framework-code-result-integrity.json"),
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    report = audit_active_results(root)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"valid={report['valid']} errors={len(report['errors'])}")
    print(f"output={output}")
    for error in report["errors"]:
        print(f"ERROR {error}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
