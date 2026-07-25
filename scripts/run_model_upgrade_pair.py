#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.models  # noqa: F401
from src.core.database import Base
from src.core.time import utc_now
from src.evaluation.concurrent_evaluator import evaluate_dimension_concurrent
from src.evaluation.prompt_builder import build_prompt
from src.evaluation.providers.factory import create_providers
from src.evaluation.schemas import DimensionResult
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework
from src.models.evaluation import AICallLog, EvaluationTask
from src.models.paper import Paper

CANDIDATE_MODELS = ("glm-5.2", "qwen3.7-max-2026-06-08")
MODEL_SET_VERSION = "two-model-upgrade-isolation-v2"
CANDIDATE_MODEL_PARAMETERS = {
    "glm-5.2": {
        "temperature": 0.3,
    },
    "qwen3.7-max-2026-06-08": {
        "temperature": 0.3,
        "enable_thinking": True,
        "thinking_budget": 4096,
        "max_completion_tokens": 8192,
    },
}


def _find_resumable_task(
    db,
    *,
    source: Path,
    framework_path: Path,
) -> tuple[Paper, EvaluationTask] | None:
    task = (
        db.query(EvaluationTask)
        .filter(
            EvaluationTask.input_file_path == str(source),
            EvaluationTask.framework_path == str(framework_path),
            EvaluationTask.model_set_version == MODEL_SET_VERSION,
            EvaluationTask.run_role == "validation",
            EvaluationTask.status.in_(("processing", "failed")),
        )
        .order_by(EvaluationTask.created_at.desc())
        .first()
    )
    if task is None:
        return None
    paper = db.get(Paper, task.paper_id)
    if paper is None:
        return None
    return paper, task


def _load_successful_results(
    db,
    *,
    task_id: str,
) -> dict[str, dict[str, DimensionResult]]:
    """从审计日志恢复已完成的维度—模型结果，供中断后续跑。"""

    logs = (
        db.query(AICallLog)
        .filter(
            AICallLog.task_id == task_id,
            AICallLog.call_type.in_(("dimension_score", "dimension_score_reuse")),
            AICallLog.status == "success",
            AICallLog.model_name.in_(CANDIDATE_MODELS),
        )
        .order_by(AICallLog.completed_at.desc(), AICallLog.created_at.desc())
        .all()
    )
    recovered: dict[str, dict[str, DimensionResult]] = {}
    for log in logs:
        model_results = recovered.setdefault(log.dimension_key, {})
        if log.model_name in model_results:
            continue
        try:
            result = DimensionResult.model_validate_json(log.response_text)
        except ValueError:
            continue
        if result.model_name != log.model_name:
            continue
        model_results[log.model_name] = result
    return recovered


def _seed_unchanged_glm_results(
    db,
    *,
    task: EvaluationTask,
    source: Path,
    framework_path: Path,
    prompts: dict[str, str],
) -> int:
    """复用配置未改变且提示完全一致的 GLM 结果，并记录审计来源。"""

    current_dimensions = {
        row.dimension_key
        for row in db.query(AICallLog)
        .filter(
            AICallLog.task_id == task.id,
            AICallLog.model_name == "glm-5.2",
            AICallLog.status == "success",
            AICallLog.call_type.in_(("dimension_score", "dimension_score_reuse")),
        )
        .all()
    }
    candidates = (
        db.query(AICallLog)
        .join(EvaluationTask, EvaluationTask.id == AICallLog.task_id)
        .filter(
            AICallLog.task_id != task.id,
            EvaluationTask.input_file_path == str(source),
            EvaluationTask.framework_path == str(framework_path),
            AICallLog.model_name == "glm-5.2",
            AICallLog.status == "success",
            AICallLog.call_type == "dimension_score",
        )
        .order_by(AICallLog.completed_at.desc(), AICallLog.created_at.desc())
        .all()
    )
    seeded = 0
    now = utc_now()
    for source_log in candidates:
        if source_log.dimension_key in current_dimensions:
            continue
        if prompts.get(source_log.dimension_key) != source_log.prompt_text:
            continue
        try:
            result = DimensionResult.model_validate_json(source_log.response_text)
        except ValueError:
            continue
        if result.model_name != "glm-5.2":
            continue
        db.add(
            AICallLog(
                task_id=task.id,
                model_name=source_log.model_name,
                provider_name=f"复用自任务:{source_log.task_id}",
                dimension_key=source_log.dimension_key,
                prompt_text=source_log.prompt_text,
                response_text=source_log.response_text,
                duration_ms=0,
                round_number=source_log.round_number,
                call_type="dimension_score_reuse",
                status="success",
                started_at=now,
                completed_at=now,
            )
        )
        current_dimensions.add(source_log.dimension_key)
        seeded += 1
    if seeded:
        db.commit()
    return seeded


def _incomplete_result_error(
    *,
    paper_id: int,
    dimension_key: str,
    results: dict[str, DimensionResult],
) -> RuntimeError:
    missing = [
        model_name for model_name in CANDIDATE_MODELS if model_name not in results
    ]
    return RuntimeError(
        f"paper-{paper_id} 的 {dimension_key} 缺少模型结果：" + "、".join(missing)
    )


async def run_manifest(
    manifest_path: Path,
    output_dir: Path,
    database_path: Path,
    *,
    batch: int | None,
    paper_id_filter: int | None = None,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("candidate_models") != list(CANDIDATE_MODELS):
        raise ValueError("清单中的候选模型与已冻结的两模型配对实验不一致")
    if manifest.get("candidate_model_parameters") != CANDIDATE_MODEL_PARAMETERS:
        raise ValueError("清单中的候选模型参数与当前冻结配置不一致")
    framework_path = Path(manifest["framework_isolation"])
    framework = load_framework(str(framework_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    for record in manifest["records"]:
        if batch is not None and record["execution_batch"] != batch:
            continue
        paper_id = int(record["paper_id"])
        if paper_id_filter is not None and paper_id != paper_id_filter:
            continue
        destination = output_dir / f"paper-{paper_id}.json"
        if destination.exists():
            print(f"skip={paper_id} reason=already_completed")
            continue
        source = Path(record["source_path"])
        if not source.exists():
            raise FileNotFoundError(f"论文源文件不存在：paper-{paper_id}")
        db = session_factory()
        paper: Paper | None = None
        task: EvaluationTask | None = None
        current_dimension = "initialization"
        try:
            resumable = _find_resumable_task(
                db,
                source=source,
                framework_path=framework_path,
            )
            if resumable is None:
                paper = Paper(
                    title=record["title"],
                    original_filename=source.name,
                    file_type=source.suffix.lstrip(".").lower(),
                    file_path=str(source),
                    status="processing",
                )
                db.add(paper)
                db.flush()
                task = EvaluationTask(
                    paper_id=paper.id,
                    framework_id=framework.version,
                    framework_path=str(framework_path),
                    input_file_path=str(source),
                    provider_names=json.dumps(CANDIDATE_MODELS),
                    model_set_version=MODEL_SET_VERSION,
                    run_role="validation",
                    status="processing",
                    cross_review_enabled=False,
                )
                db.add(task)
            else:
                paper, task = resumable
                paper.status = "processing"
                task.status = "processing"
                task.failure_stage = None
                task.failure_detail = None
            db.commit()
            processed = process_file(str(source))
            prompts = {
                dimension.key: build_prompt(dimension, processed)
                for dimension in framework.dimensions
            }
            seeded_count = _seed_unchanged_glm_results(
                db,
                task=task,
                source=source,
                framework_path=framework_path,
                prompts=prompts,
            )
            recovered = _load_successful_results(db, task_id=task.id)
            recovered_count = sum(len(values) for values in recovered.values())
            if recovered_count:
                print(
                    f"paper={paper_id} resume_results={recovered_count} "
                    f"seeded_results={seeded_count} task={task.id}"
                )
            dimensions: dict[str, dict] = {}
            for dimension in framework.dimensions:
                current_dimension = dimension.key
                existing = recovered.setdefault(dimension.key, {})
                missing_models = [
                    model_name
                    for model_name in CANDIDATE_MODELS
                    if model_name not in existing
                ]
                print(
                    f"paper={paper_id} dimension={dimension.key} "
                    f"pending_models={','.join(missing_models) or 'none'}"
                )
                if missing_models:
                    results = await evaluate_dimension_concurrent(
                        create_providers(missing_models),
                        dimension,
                        processed,
                        task.id,
                        db,
                    )
                    existing.update({result.model_name: result for result in results})
                if set(existing) != set(CANDIDATE_MODELS):
                    raise _incomplete_result_error(
                        paper_id=paper_id,
                        dimension_key=dimension.key,
                        results=existing,
                    )
                dimensions[dimension.key] = {
                    "name_zh": dimension.name_zh,
                    "scores": {
                        model_name: existing[model_name].score
                        for model_name in CANDIDATE_MODELS
                    },
                    "results": {
                        model_name: existing[model_name].model_dump()
                        for model_name in CANDIDATE_MODELS
                    },
                }
            task.status = "completed"
            task.failure_stage = None
            task.failure_detail = None
            paper.status = "completed"
            db.commit()
            payload = {
                "paper_id": paper_id,
                "journal": record["journal"],
                "framework": str(framework_path),
                "models": list(CANDIDATE_MODELS),
                "model_parameters": CANDIDATE_MODEL_PARAMETERS,
                "model_set_version": MODEL_SET_VERSION,
                "dimensions": dimensions,
                "audit_database": str(database_path),
                "sample_manifest_sha256": manifest["manifest_sha256"],
            }
            temporary = destination.with_suffix(".json.part")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(destination)
        except Exception as exc:
            db.rollback()
            if task is not None:
                task.status = "failed"
                task.failure_stage = f"dimension:{current_dimension}"[:50]
                task.failure_detail = f"{exc.__class__.__name__}: {exc}"[:4000]
            if paper is not None:
                paper.status = "failed"
            if task is not None or paper is not None:
                db.commit()
            raise
        finally:
            db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="经统一 Provider 层运行两款新模型的 v2.55 隔离配对实验。"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("output/model-upgrade/paired-sample-manifest.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/model-upgrade/candidate-results"),
    )
    parser.add_argument(
        "--audit-database",
        type=Path,
        default=Path("output/model-upgrade/model-calls.sqlite"),
    )
    parser.add_argument("--batch", type=int, choices=(1, 2, 3))
    parser.add_argument(
        "--paper-id",
        type=int,
        help="只执行指定论文；用于失败后的受控恢复验证",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="确认发起真实模型调用；不提供时只做配置检查",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("sample_count") != 24:
        raise ValueError("配对实验必须使用冻结的 24 篇样本清单")
    if not args.execute:
        print(
            "配置检查通过；如已批准模型费用，添加 --execute，"
            "并建议依次使用 --batch 1、2、3。"
        )
        return
    asyncio.run(
        run_manifest(
            args.manifest,
            args.output_dir,
            args.audit_database,
            batch=args.batch,
            paper_id_filter=args.paper_id,
        )
    )


if __name__ == "__main__":
    main()
