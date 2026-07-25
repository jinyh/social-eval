import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.models  # noqa: F401
from scripts.run_model_upgrade_pair import (
    MODEL_SET_VERSION,
    _find_resumable_task,
    _load_successful_results,
    _seed_unchanged_glm_results,
)
from src.core.database import Base
from src.models.evaluation import AICallLog, EvaluationTask
from src.models.paper import Paper


def test_recovers_successful_model_result_from_audit_log(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.sqlite'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    source = tmp_path / "paper-152.pdf"
    framework = Path("configs/frameworks/law-v2.55-cross-review.yaml")
    paper = Paper(
        title="测试论文",
        original_filename=source.name,
        file_type="pdf",
        file_path=str(source),
        status="failed",
    )
    db.add(paper)
    db.flush()
    task = EvaluationTask(
        paper_id=paper.id,
        framework_id="law-v2.55",
        framework_path=str(framework),
        input_file_path=str(source),
        provider_names=json.dumps(["glm-5.2", "qwen3.7-max-2026-06-08"]),
        model_set_version=MODEL_SET_VERSION,
        run_role="validation",
        status="failed",
        cross_review_enabled=False,
    )
    db.add(task)
    db.flush()
    db.add(
        AICallLog(
            task_id=task.id,
            model_name="glm-5.2",
            provider_name="DashScopeProvider",
            dimension_key="analytical_framework",
            prompt_text="prompt",
            response_text=json.dumps(
                {
                    "dimension": "analytical_framework",
                    "score": 81,
                    "evidence_quotes": ["证据"],
                    "model_name": "glm-5.2",
                },
                ensure_ascii=False,
            ),
            duration_ms=100,
            round_number=1,
            call_type="dimension_score",
            status="success",
        )
    )
    db.commit()

    resumable = _find_resumable_task(
        db,
        source=source,
        framework_path=framework,
    )
    recovered = _load_successful_results(db, task_id=task.id)

    assert resumable == (paper, task)
    assert recovered["analytical_framework"]["glm-5.2"].score == 81
    db.close()
    engine.dispose()


def test_seeds_unchanged_glm_result_with_audit_provenance(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'reuse.sqlite'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    source = tmp_path / "paper-152.pdf"
    framework = Path("configs/frameworks/law-v2.55-cross-review.yaml")
    paper = Paper(
        title="测试论文",
        original_filename=source.name,
        file_type="pdf",
        file_path=str(source),
        status="processing",
    )
    db.add(paper)
    db.flush()
    old_task = EvaluationTask(
        paper_id=paper.id,
        framework_id="law-v2.55",
        framework_path=str(framework),
        input_file_path=str(source),
        model_set_version="two-model-upgrade-isolation-v1",
        run_role="validation",
        status="failed",
        cross_review_enabled=False,
    )
    new_task = EvaluationTask(
        paper_id=paper.id,
        framework_id="law-v2.55",
        framework_path=str(framework),
        input_file_path=str(source),
        model_set_version=MODEL_SET_VERSION,
        run_role="validation",
        status="processing",
        cross_review_enabled=False,
    )
    db.add_all([old_task, new_task])
    db.flush()
    db.add(
        AICallLog(
            task_id=old_task.id,
            model_name="glm-5.2",
            provider_name="DashScopeProvider",
            dimension_key="analytical_framework",
            prompt_text="same prompt",
            response_text=json.dumps(
                {
                    "dimension": "analytical_framework",
                    "score": 81,
                    "evidence_quotes": ["证据"],
                    "model_name": "glm-5.2",
                },
                ensure_ascii=False,
            ),
            duration_ms=100,
            round_number=1,
            call_type="dimension_score",
            status="success",
        )
    )
    db.commit()

    seeded = _seed_unchanged_glm_results(
        db,
        task=new_task,
        source=source,
        framework_path=framework,
        prompts={"analytical_framework": "same prompt"},
    )
    reused = (
        db.query(AICallLog)
        .filter(
            AICallLog.task_id == new_task.id,
            AICallLog.call_type == "dimension_score_reuse",
        )
        .one()
    )

    assert seeded == 1
    assert reused.model_name == "glm-5.2"
    assert old_task.id in reused.provider_name
    db.close()
    engine.dispose()
