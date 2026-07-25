import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.upgrade_editorial_reports_v4 as upgrade_script
import src.models  # noqa: F401
from src.core.database import Base
from src.models.editorial import EditorialDocument, EditorialSubmission


def test_upgrade_reports_appends_v4_once_and_preserves_v3(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'reports.sqlite'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    submission = EditorialSubmission(
        unit_id="unit-1",
        paper_id="paper-1",
        evaluation_task_id="task-1",
        title="测试投稿",
        status="completed",
        recommendation_state="ready",
        policy_key="jiaoda-law-v1",
        policy_version="1.0",
        current_report_version=3,
        created_by="editor-1",
    )
    db.add(submission)
    db.flush()
    old_path = tmp_path / "report-v3.json"
    old_path.write_text(
        json.dumps({"schema_version": "editorial-report-v3"}),
        encoding="utf-8",
    )
    db.add(
        EditorialDocument(
            submission_id=submission.id,
            kind="report_json",
            version=3,
            file_path=str(old_path),
            sha256="0" * 64,
        )
    )
    db.commit()

    def fake_generate(session, submission_id):
        row = session.get(EditorialSubmission, submission_id)
        version = row.current_report_version + 1
        new_path = tmp_path / f"report-v{version}.json"
        payload = {"schema_version": upgrade_script.TARGET_SCHEMA_VERSION}
        new_path.write_text(json.dumps(payload), encoding="utf-8")
        session.add(
            EditorialDocument(
                submission_id=submission_id,
                kind="report_json",
                version=version,
                file_path=str(new_path),
                sha256="1" * 64,
            )
        )
        row.current_report_version = version
        session.commit()
        return version, payload

    monkeypatch.setattr(upgrade_script, "generate_editorial_report", fake_generate)

    assert upgrade_script.upgrade_reports(db, execute=True) == (1, 1)
    assert upgrade_script.upgrade_reports(db, execute=True) == (0, 0)
    assert old_path.exists()
    assert db.get(EditorialSubmission, submission.id).current_report_version == 4

    db.close()
    engine.dispose()


def test_upgrade_reports_rebuilds_v4_with_english_band_codes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'english.sqlite'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    submission = EditorialSubmission(
        id="submission-english-band",
        unit_id="unit-1",
        paper_id="paper-1",
        evaluation_task_id="task-1",
        status="completed",
        recommendation_state="withheld",
        policy_key="jiaoda-law-v1",
        policy_version="1",
        created_by="user-1",
        current_report_version=1,
    )
    path = tmp_path / "report-v1.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": upgrade_script.TARGET_SCHEMA_VERSION,
                "ai_opinions": [
                    {
                        "type": "ai_synthesis",
                        "content": {"disagreement_points": ["excellent 与 good"]},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    db.add(submission)
    db.add(
        EditorialDocument(
            submission_id=submission.id,
            kind="report_json",
            version=1,
            file_path=str(path),
            sha256="sha",
        )
    )
    db.commit()
    generated: list[str] = []

    def fake_generate(_db, submission_id):
        generated.append(submission_id)
        return 2, {}

    monkeypatch.setattr(upgrade_script, "generate_editorial_report", fake_generate)

    assert upgrade_script.upgrade_reports(db, execute=True) == (1, 1)
    assert generated == [submission.id]
    db.close()
    engine.dispose()
