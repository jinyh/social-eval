# 六维 AI 初筛加权与分流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留六维名称和 100 分制的前提下，落地新的权重、核心分、异常标记与分流决策，并让内部报告与复核队列能够使用这些结果。

**Architecture:** 以“新框架配置 + 报告构建层计算 + 队列读取报告决策”为主线，不改数据库 schema。权重和维度角色放进新 framework YAML；`src/reporting/` 新增集中计算逻辑；`src/review/queue.py` 只消费当前报告快照，不重复实现分流规则。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Pydantic, PyYAML, pytest

---

### Task 1: 新框架与默认框架入口

**Files:**
- Create: `configs/frameworks/law-v2.19-20260424.yaml`
- Modify: `src/api/routers/papers.py`
- Test: `tests/test_knowledge/test_law_v2_19_research_framework.py`
- Test: `tests/test_api/test_papers_router.py`

- [ ] **Step 1: 先写失败测试，锁定新框架权重与角色**

```python
from pathlib import Path
import yaml

FRAMEWORK_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "frameworks"
    / "law-v2.19-20260424.yaml"
)


def test_v2_19_weights_and_roles_match_weighted_routing_scheme():
    framework = yaml.safe_load(FRAMEWORK_PATH.read_text(encoding="utf-8"))
    dims = {d["key"]: d for d in framework["dimensions"]}

    assert dims["problem_originality"]["weight"] == 0.20
    assert dims["literature_insight"]["weight"] == 0.15
    assert dims["analytical_framework"]["weight"] == 0.20
    assert dims["logical_coherence"]["weight"] == 0.30
    assert dims["conclusion_consensus"]["weight"] == 0.10
    assert dims["forward_extension"]["weight"] == 0.05
    assert dims["problem_originality"]["dimension_role"] == "core"
    assert dims["forward_extension"]["dimension_role"] == "auxiliary"
```

- [ ] **Step 2: 运行测试，确认红灯**

Run: `uv run pytest tests/test_knowledge/test_law_v2_19_research_framework.py -q`

Expected: 因框架文件不存在或字段缺失而失败。

- [ ] **Step 3: 再写默认框架入口测试**

在 `tests/test_api/test_papers_router.py` 增加断言：

```python
task = db_session.query(EvaluationTask).filter(EvaluationTask.paper_id == payload["paper_id"]).first()
assert task.framework_path == "configs/frameworks/law-v2.19-20260424.yaml"
```

- [ ] **Step 4: 运行入口测试，确认红灯**

Run: `uv run pytest tests/test_api/test_papers_router.py::test_upload_txt_file_runs_pipeline_and_persists_results -q`

Expected: 由于默认 framework path 仍指向旧版而失败。

- [ ] **Step 5: 实现最小配置改动**

实现要求：

- 以 `law-v2.18-20260424.yaml` 为基础复制出 `law-v2.19-20260424.yaml`
- 仅做本次方案需要的配置变更：
  - 六维权重改为 `20/15/20/30/10/5`
  - 为每个维度补 `dimension_role: core|auxiliary`
  - 在 `scoring_structure` 或顶层增加可供报告层读取的分流参数：
    - `core_dimension_keys`
    - `forward_extension_disabled_below`
    - `routing_thresholds`
    - `anomaly_rules`
- 把 `src/api/routers/papers.py` 中的 `DEFAULT_FRAMEWORK_PATH` 改为新文件

- [ ] **Step 6: 重新运行测试，确认转绿**

Run:

```bash
uv run pytest tests/test_knowledge/test_law_v2_19_research_framework.py -q
uv run pytest tests/test_api/test_papers_router.py::test_upload_txt_file_runs_pipeline_and_persists_results -q
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add configs/frameworks/law-v2.19-20260424.yaml src/api/routers/papers.py \
  tests/test_knowledge/test_law_v2_19_research_framework.py tests/test_api/test_papers_router.py
git commit -m "feat: add weighted six-dimension default framework"
```

### Task 2: 报告层核心分、异常标记与分流决策

**Files:**
- Create: `src/reporting/scoring.py`
- Modify: `src/reporting/builder.py`
- Modify: `src/reporting/public_filter.py`
- Test: `tests/test_api/test_reports_and_reviews.py`

- [ ] **Step 1: 先写失败测试，锁定内部报告输出结构**

在 `tests/test_api/test_reports_and_reviews.py` 新增用例，上传论文后手工改写各维 `ReliabilityResult`：

```python
def test_internal_report_exposes_core_score_routing_and_anomaly_flags(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter")
    create_user(db_session, email="editor@example.com", role="editor")

    _login(client, "submitter@example.com")
    payload = _upload_with_scores(client, [70, 70, 70])

    task = db_session.query(EvaluationTask).filter(EvaluationTask.id == payload["task_id"]).first()
    task.framework_path = "configs/frameworks/law-v2.19-20260424.yaml"

    overrides = {
        "problem_originality": (58, 2.0),
        "literature_insight": (62, 2.0),
        "analytical_framework": (82, 2.0),
        "logical_coherence": (45, 2.0),
        "conclusion_consensus": (78, 2.0),
        "forward_extension": (85, 2.0),
    }
    for row in db_session.query(ReliabilityResult).filter(ReliabilityResult.task_id == task.id):
        row.mean_score, row.std_score = overrides[row.dimension_key]
        row.is_high_confidence = True
    db_session.commit()

    client.cookies.clear()
    _login(client, "editor@example.com")
    body = client.get(f"/api/papers/{payload['paper_id']}/internal-report").json()

    assert body["weighted_total"] == 58.6
    assert body["core_score"] == 59.76
    assert body["routing_decision"] == "reject_or_major_revision"
    assert "extension_without_core_support" in body["anomaly_flags"]
    assert "high_conclusion_low_logic" in body["anomaly_flags"]
    assert body["dimensions"][0]["dimension_role"] in {"core", "auxiliary"}
```

- [ ] **Step 2: 运行该测试，确认红灯**

Run: `uv run pytest tests/test_api/test_reports_and_reviews.py::test_internal_report_exposes_core_score_routing_and_anomaly_flags -q`

Expected: 因缺少 `core_score` / `routing_decision` / `anomaly_flags` 字段失败。

- [ ] **Step 3: 实现集中计算模块**

在 `src/reporting/scoring.py` 实现以下纯函数：

```python
def build_dimension_profiles(framework, reliability_rows) -> list[dict]: ...
def calculate_weighted_total(profiles: list[dict]) -> float: ...
def calculate_core_score(profiles: list[dict]) -> float: ...
def calculate_dimension_confidence(std_score: float) -> str: ...
def detect_anomaly_flags(profiles: list[dict]) -> list[str]: ...
def build_routing_decision(profiles: list[dict], weighted_total: float) -> tuple[str, list[str]]: ...
```

规则固定如下：

- `core` 维度：问题创新性、现状洞察度、分析框架建构力、逻辑严密性
- `auxiliary` 维度：结论可接受性、前瞻延展性
- `core_score` = 核心四维加权和 / `0.85`
- 当 `logical_coherence < 60` 或 `conclusion_consensus < 60` 时，`forward_extension` 的总分贡献记为 `0`
- 当 `forward_extension > 70` 且任一核心维度 `< 50`，标记 `extension_without_core_support`
- 当 `conclusion_consensus > 70` 且 `logical_coherence < 50`，标记 `high_conclusion_low_logic`
- 当 `analytical_framework > 75` 且 `literature_insight < 40`，标记 `high_framework_low_literature`
- 置信度等级：
  - `std <= 5`: `high`
  - `5 < std <= 8`: `medium`
  - `8 < std <= 12`: `low`
  - `std > 12`: `critical`
- 分流：
  - 任一核心维度 `critical` -> `manual_review`
  - 两个及以上核心维度 `low/critical` -> `manual_review`
  - 否则若 `weighted_total >= 75` -> `fast_track_review`
  - 否则若 `weighted_total < 60` -> `reject_or_major_revision`
  - 其他 -> `manual_review`

- [ ] **Step 4: 把计算接入内部/公开报告**

在 `src/reporting/builder.py`：

- 用新 helper 统一生成维度 profile
- 在每个维度输出中补：
  - `dimension_role`
  - `ai.confidence_level`
- 在报告顶层补：
  - `core_score`
  - `routing_decision`
  - `routing_reasons`
  - `anomaly_flags`

在 `src/reporting/public_filter.py`：

- 保留 `weighted_total`
- 不向公开报告暴露 `routing_reasons`
- 可保留 `core_score` 与 `routing_decision` 之外的现状，避免把内部分流逻辑直接暴露给投稿人

- [ ] **Step 5: 跑测试确认转绿**

Run:

```bash
uv run pytest tests/test_api/test_reports_and_reviews.py::test_internal_report_exposes_core_score_routing_and_anomaly_flags -q
uv run pytest tests/test_api/test_reports_and_reviews.py::test_internal_and_public_report_endpoints_expose_different_detail_levels -q
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/reporting/scoring.py src/reporting/builder.py src/reporting/public_filter.py \
  tests/test_api/test_reports_and_reviews.py
git commit -m "feat: add weighted routing metadata to reports"
```

### Task 3: 复核队列消费新的分流结果

**Files:**
- Modify: `src/review/queue.py`
- Modify: `src/api/schemas/reviews.py`
- Test: `tests/test_api/test_reports_and_reviews.py`

- [ ] **Step 1: 先写失败测试，锁定“中分但高置信度”进入人工复核**

在 `tests/test_api/test_reports_and_reviews.py` 增加用例：

```python
def test_manual_review_routing_can_enqueue_task_without_low_confidence(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter")
    create_user(db_session, email="editor@example.com", role="editor")

    _login(client, "submitter@example.com")
    payload = _upload_with_scores(client, [70, 70, 70])

    task = db_session.query(EvaluationTask).filter(EvaluationTask.id == payload["task_id"]).first()
    task.framework_path = "configs/frameworks/law-v2.19-20260424.yaml"

    overrides = {
        "problem_originality": (70, 2.0),
        "literature_insight": (68, 2.0),
        "analytical_framework": (72, 2.0),
        "logical_coherence": (69, 2.0),
        "conclusion_consensus": (66, 2.0),
        "forward_extension": (55, 2.0),
    }
    for row in db_session.query(ReliabilityResult).filter(ReliabilityResult.task_id == task.id):
        row.mean_score, row.std_score = overrides[row.dimension_key]
        row.is_high_confidence = True
    db_session.commit()

    client.cookies.clear()
    _login(client, "editor@example.com")
    queue = client.get("/api/reviews/queue").json()["items"]

    assert queue[0]["task_id"] == payload["task_id"]
    assert queue[0]["routing_decision"] == "manual_review"
    assert queue[0]["low_confidence_dimensions"] == []
```

- [ ] **Step 2: 运行测试，确认红灯**

Run: `uv run pytest tests/test_api/test_reports_and_reviews.py::test_manual_review_routing_can_enqueue_task_without_low_confidence -q`

Expected: 当前队列只看 `is_high_confidence`，测试失败。

- [ ] **Step 3: 最小实现**

在 `src/review/queue.py`：

- 先保持原有 `low_confidence_rows` 逻辑
- 再读取当前 internal report：
  - 若 `routing_decision == "manual_review"`，即使没有低置信度维度也入队
- 队列项新增：
  - `routing_decision`
  - `routing_reasons`

在 `src/api/schemas/reviews.py` 同步加字段：

```python
routing_decision: str | None = None
routing_reasons: list[str] = []
```

- [ ] **Step 4: 跑相关测试确认转绿**

Run:

```bash
uv run pytest tests/test_api/test_reports_and_reviews.py::test_manual_review_routing_can_enqueue_task_without_low_confidence -q
uv run pytest tests/test_api/test_reports_and_reviews.py::test_low_confidence_task_appears_in_review_queue_and_editor_can_assign_expert -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/review/queue.py src/api/schemas/reviews.py tests/test_api/test_reports_and_reviews.py
git commit -m "feat: route manual review tasks into review queue"
```

### Task 4: 全链路回归与文档补充

**Files:**
- Modify: `docs/evaluation/how-to-use-law-v2-config.md`
- Modify: `docs/evaluation/README-20260423.md`
- Test: `tests/test_api/test_reports_and_reviews.py`
- Test: `tests/test_api/test_papers_router.py`
- Test: `tests/test_reporting/test_simple_pdf_builder.py`

- [ ] **Step 1: 补失败测试，防止简单 PDF/导出被新字段破坏**

补一个最小断言，确保带有 `core_score` / `routing_decision` 的公开报告仍可导出：

```python
assert pdf_export.content.startswith(b"%PDF")
```

如果已有测试覆盖，直接复用，不再新增重复测试。

- [ ] **Step 2: 跑回归测试**

Run:

```bash
uv run pytest tests/test_api/test_papers_router.py -q
uv run pytest tests/test_api/test_reports_and_reviews.py -q
uv run pytest tests/test_reporting/test_simple_pdf_builder.py -q
uv run pytest tests/test_knowledge/test_law_v2_19_research_framework.py -q
```

Expected: 全绿。

- [ ] **Step 3: 更新文档**

补充两点即可，不做长篇重写：

- `docs/evaluation/how-to-use-law-v2-config.md`
  - 默认框架版本改为 `v2.19`
  - 增加 `core_score / routing_decision / anomaly_flags` 说明
- `docs/evaluation/README-20260423.md`
  - 增加“六维保留但分层使用”的实现说明

- [ ] **Step 4: 再跑一次最小回归**

Run:

```bash
uv run pytest tests/test_api/test_reports_and_reviews.py::test_internal_and_public_report_endpoints_expose_different_detail_levels -q
uv run pytest tests/test_api/test_reports_and_reviews.py::test_manual_review_routing_can_enqueue_task_without_low_confidence -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/evaluation/how-to-use-law-v2-config.md docs/evaluation/README-20260423.md
git commit -m "docs: describe weighted routing report fields"
```

## Acceptance Criteria

- 默认上传任务使用 `law-v2.19-20260424.yaml`
- 内部报告包含 `weighted_total`、`core_score`、`routing_decision`、`routing_reasons`、`anomaly_flags`
- 维度项包含 `dimension_role`，AI 结果包含 `confidence_level`
- `forward_extension` 在 `logical_coherence < 60` 或 `conclusion_consensus < 60` 时不再拉高总分
- “中分但高置信度”的任务可以凭 `routing_decision == manual_review` 进入复核队列
- 不新增数据库迁移
- 公开报告仍能正常导出 JSON/PDF

## Notes

- 本计划刻意不改 `EvaluationTask` / `Report` 数据库字段，避免 schema 迁移扩散
- 若实现时发现公开报告也必须展示 `routing_decision`，只做字段透传，不改变公开界面的默认呈现
- 若队列语义需要区分“专家复核”和“编辑人工判断”，可在下一轮把 `manual_review` 再拆成更细的内部动作，但本轮不做
