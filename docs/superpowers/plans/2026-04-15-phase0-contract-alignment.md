# Phase 0 Contract Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the declared law v2.0 framework actually load, render prompts correctly, and pass tests as the active contract baseline.

**Architecture:** Keep a normalized `Framework` model as the runtime contract, let the loader detect legacy v1 vs v2 raw shapes, and centralize prompt rendering so old placeholder templates and new literal-JSON templates both work.

**Tech Stack:** Python 3.12, pytest, pydantic, jsonschema, YAML

---

### Task 1: Stabilize test execution and codify the v2 baseline

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_knowledge/test_loader.py`
- Modify: `tests/test_evaluation/test_prompt_builder.py`

- [ ] **Step 1: Add failing tests for v2 loader + v2 prompt rendering**

Add tests that require:
- loading `configs/frameworks/law-v2.0-20260413.yaml`
- exposing normalized `name / discipline / version / std_threshold`
- rendering v2 dimension prompts with paper content and references
- rendering v2 precheck prompts with paper content

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `uv run pytest tests/test_knowledge/test_loader.py tests/test_evaluation/test_prompt_builder.py -q`

Expected: FAIL because current loader still validates against v1 schema and prompt builder still uses `.format()` on v2 literal JSON templates.

### Task 2: Normalize the framework contract

**Files:**
- Modify: `src/knowledge/schemas.py`
- Modify: `src/knowledge/loader.py`
- Modify: `configs/frameworks/schema_v2.json`
- Modify: `configs/frameworks/law-v2.0-20260413.yaml`

- [ ] **Step 1: Implement normalized framework models**

Add optional structured v2 sections while preserving the runtime fields used by existing code:
- `name`
- `discipline`
- `version`
- `std_threshold`
- `dimensions`

- [ ] **Step 2: Detect and load v1/v2 raw configs**

Support:
- legacy top-level v1 shape
- v2 `metadata + precheck + scoring_structure + dimensions + ...` shape

- [ ] **Step 3: Fix the v2 raw contract**

Align `schema_v2.json` and `law-v2.0-20260413.yaml` around the actual system contract:
- six dimensions
- total score 100
- no `bonus`
- explicit `std_threshold`

- [ ] **Step 4: Run focused loader tests**

Run: `uv run pytest tests/test_knowledge/test_loader.py -q`

Expected: PASS

### Task 3: Centralize prompt rendering behavior

**Files:**
- Modify: `src/evaluation/prompt_builder.py`
- Modify: `tests/test_evaluation/test_prompt_builder.py`

- [ ] **Step 1: Implement placeholder-aware prompt rendering**

Rules:
- if template uses `{paper_content}` / `{references}` -> format it
- otherwise append standardized paper context without calling `.format()`

- [ ] **Step 2: Add precheck prompt rendering helper**

Expose a helper for later orchestration work so v2 precheck can be rendered safely now.

- [ ] **Step 3: Run focused prompt tests**

Run: `uv run pytest tests/test_evaluation/test_prompt_builder.py -q`

Expected: PASS

### Task 4: Refresh the roadmap and verify the phase

**Files:**
- Create: `development-roadmap.md`
- Modify: `README.md`

- [ ] **Step 1: Rewrite the roadmap with phase 0-5 ordering**

Reflect the approved strategy:
- phase 0 contract alignment
- phase 1 platform/auth
- phase 2 pipeline MVP
- phase 3 reports/review
- phase 4 state/audit/recovery
- phase 5 frontend

- [ ] **Step 2: Refresh README references that still point at old requirement versions**

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -q`

Expected: PASS
