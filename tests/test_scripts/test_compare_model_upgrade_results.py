import sqlite3
from pathlib import Path

from scripts.compare_model_upgrade_results import _operational_metrics


def test_operational_metrics_include_retries_and_reuse(tmp_path: Path):
    database = tmp_path / "audit.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE evaluation_tasks (
            id TEXT PRIMARY KEY,
            model_set_version TEXT NOT NULL
        );
        CREATE TABLE ai_call_logs (
            task_id TEXT NOT NULL,
            dimension_key TEXT NOT NULL,
            model_name TEXT NOT NULL,
            call_type TEXT NOT NULL,
            status TEXT NOT NULL,
            duration_ms INTEGER NOT NULL
        );
        INSERT INTO evaluation_tasks VALUES ('task-1', 'candidate-v2');
        INSERT INTO ai_call_logs VALUES
            ('task-1', 'dimension-a', 'qwen', 'dimension_score', 'failed', 10),
            ('task-1', 'dimension-a', 'qwen', 'dimension_score', 'success', 30),
            ('task-1', 'dimension-b', 'qwen', 'dimension_score', 'success', 50),
            ('task-1', 'dimension-a', 'glm', 'dimension_score_reuse', 'success', 0);
        """
    )
    connection.commit()
    connection.close()

    metrics = {
        item["candidate_model"]: item
        for item in _operational_metrics(
            database,
            model_set_version="candidate-v2",
        )
    }

    assert metrics["qwen"]["failed_attempts"] == 1
    assert metrics["qwen"]["units_requiring_retry"] == 1
    assert metrics["qwen"]["unit_retry_rate"] == 0.5
    assert metrics["qwen"]["mean_success_duration_ms"] == 40.0
    assert metrics["glm"]["reused_results"] == 1
