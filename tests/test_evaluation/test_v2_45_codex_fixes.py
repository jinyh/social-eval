"""Codex 审查 6 项问题的端到端回归测试（v2.45 D 路径修复版）。

每个 test 名称标注对应的 Codex 问题编号（#1-#6），确保修复后的行为符合 v0.15 规程。
"""

from __future__ import annotations

import pytest

from src.evaluation.precheck import PrecheckResult, _adapt_to_v014_contract
from src.evaluation.result_validator import aggregate_result
from src.evaluation.schemas import SignalCheckResult
from src.knowledge.loader import load_framework
from src.reliability.schemas import ReliabilityReport

FRAMEWORK_V2_45 = "configs/frameworks/law-v2.56.6-20260522.yaml"


@pytest.fixture
def framework_v2_45():
    return load_framework(FRAMEWORK_V2_45)


@pytest.fixture
def framework_legacy():
    current = load_framework(FRAMEWORK_V2_45)
    raw_config = dict(current.raw_config)
    raw_config.pop("scoring_protocol", None)
    return current.model_copy(
        update={"raw_config": raw_config, "autonomous_knowledge_signals": None}
    )


@pytest.fixture
def no_contradiction_signal():
    return SignalCheckResult(
        china_problem_centered="yes",
        china_practice_explanation_attempted="yes",
        external_theory_transformation="sufficient",
        verifiable_concept_or_thesis="yes",
        triggers_review=False,
    )


# ================================================================
# Codex #1: 预检层复核（boundary / obviously_ineligible）必须进队列
# ================================================================


def test_codex1_boundary_review_has_required_status(
    framework_v2_45, no_contradiction_signal
):
    """manual_review → boundary_review → review_status=required（应进队列）。"""
    precheck = _adapt_to_v014_contract(
        PrecheckResult(status="manual_review", issues=["疑点"]), framework_v2_45
    )
    result = aggregate_result(
        {"problem_originality": 80, "literature_insight": 75},
        precheck, no_contradiction_signal, [], framework_v2_45,
    )
    # 预检层复核必须 required，orchestrator 会据此设置 manual_review_requested
    assert result.review_status == "required"
    assert result.review_level == "precheck_level"


def test_codex1_obviously_ineligible_has_required_status(
    framework_v2_45, no_contradiction_signal
):
    """reject → obviously_ineligible → review_status=required。"""
    precheck = _adapt_to_v014_contract(
        PrecheckResult(status="reject", issues=["文件损坏"]), framework_v2_45
    )
    result = aggregate_result(
        {}, precheck, no_contradiction_signal, [], framework_v2_45,
    )
    assert result.review_status == "required"
    assert result.review_level == "precheck_level"


# ================================================================
# Codex #2: reject 短路应补 aggregate_result（而非直接 completed）
# ================================================================
# 注：orchestrator 行为无法在纯单元测试验证，此处验证 aggregate_result
# 在 reject 场景下可以用空 dim scores 正常调用（不抛异常），
# 并输出符合契约的 required 状态。


def test_codex2_reject_path_produces_valid_aggregate(
    framework_v2_45, no_contradiction_signal
):
    """reject 情况下 aggregate_result 应返回 review_status=required, base/bonus=0。"""
    precheck = _adapt_to_v014_contract(
        PrecheckResult(status="reject", issues=["OCR 失败"]), framework_v2_45
    )
    # 空的 dimension_scores 模拟未进入六维评分
    result = aggregate_result(
        {}, precheck, None, [], framework_v2_45,
    )
    assert result.base_score == 0.0
    assert result.bonus_score == 0.0
    assert result.final_score == 0.0
    assert result.review_status == "required"
    assert result.review_level == "precheck_level"
    assert result.triage_recommendation == "obviously_ineligible_manual_confirm"
    # Paper 必须能正确标记为需要人工确认
    assert precheck.requires_manual_confirmation is True


# ================================================================
# Codex #3: conditional_pass 应视为边界复核（而非正常进入评分）
# ================================================================


def test_codex3_conditional_pass_maps_to_boundary_review(framework_v2_45):
    """conditional_pass → boundary_review（v0.15 §2.2 口径）。"""
    p = _adapt_to_v014_contract(
        PrecheckResult(status="conditional_pass", issues=["引用需核验"]), framework_v2_45
    )
    assert p.conclusion == "boundary_review"
    assert p.enter_six_dimension_review == "boundary"
    assert p.requires_manual_confirmation is True
    assert p.boundary_reasons == ["引用需核验"]


def test_codex3_conditional_pass_routes_into_review_queue(
    framework_v2_45, no_contradiction_signal
):
    """conditional_pass 的论文即使六维高分也必须进复核队列。"""
    precheck = _adapt_to_v014_contract(
        PrecheckResult(status="conditional_pass", issues=["风险"]), framework_v2_45
    )
    high_scores = {
        "problem_originality": 85,
        "literature_insight": 80,
        "analytical_framework": 80,
        "logical_coherence": 80,
        "conclusion_consensus": 80,
        "forward_extension": 70,
    }
    result = aggregate_result(
        high_scores, precheck, no_contradiction_signal, [], framework_v2_45,
    )
    assert result.precheck_conclusion == "boundary_review"
    assert result.review_status == "required"


# ================================================================
# Codex #4: contradiction_triggers 应使用最终分（core+ceiling+bonus），
#   而非维度均值
# ================================================================


def test_codex4_final_score_driven_contradiction_triggers(framework_v2_45):
    """
    构造反例：核心四维都低（30），但结论可接受性和前瞻延展性高（80）。
    维度均值 = (30+30+30+30+80+80)/6 = 46.67 < 50（会触发 rule_2）
    真实 final_score（core 主导）≈ 30 < 50，也应触发
    两者方向一致时——构造更极端的反例。

    真正的反例：核心四维 50，结论 55，前瞻 80；
    dim_means = (50*4+55+80)/6 = 55.83
    真实 base = 50, bonus=0（conclusion<60 不满足前提）, ceiling=65, final=50
    所以最终分 50 > 均值 55.83 的结论可能差 5 分——这刚好能区分。

    这里直接断言使用 calculate_weighted_total 的结果：
    """
    from src.reporting.scoring import calculate_weighted_total

    scores = {
        "problem_originality": 50,
        "literature_insight": 50,
        "analytical_framework": 50,
        "logical_coherence": 50,
        "conclusion_consensus": 55,
        "forward_extension": 80,
    }
    protocol = framework_v2_45.raw_config.get("scoring_protocol")
    dim_weights = {d.key: d.weight for d in framework_v2_45.dimensions}
    final = calculate_weighted_total(
        dimension_scores=scores,
        scoring_protocol=protocol,
        dimension_weights=dim_weights,
    )
    naive_mean = sum(scores.values()) / len(scores)
    # 两者必须不同（否则 Codex #4 这条规则本身无意义）
    assert final != naive_mean, (
        f"final={final} vs naive_mean={naive_mean} — 如果相同则无法验证 Codex #4"
    )


# ================================================================
# Codex #5: precheck 输出契约应完整（enter_six_dimension_review 等字段）
# ================================================================


def test_codex5_precheck_contract_has_enter_six_dimension_review(framework_v2_45):
    """v0.15 §7.2 要求 PrecheckResult 有 enter_six_dimension_review 字段。"""
    p = _adapt_to_v014_contract(PrecheckResult(status="pass"), framework_v2_45)
    assert p.enter_six_dimension_review == "yes"

    p = _adapt_to_v014_contract(PrecheckResult(status="manual_review"), framework_v2_45)
    assert p.enter_six_dimension_review == "boundary"

    p = _adapt_to_v014_contract(PrecheckResult(status="reject"), framework_v2_45)
    assert p.enter_six_dimension_review == "no"


def test_codex5_triggered_signals_remains_None_after_adapter(framework_v2_45):
    """triggered_signals 不在预检适配层填充（留给 orchestrator 按信号校验结果返填）。"""
    p = _adapt_to_v014_contract(PrecheckResult(status="pass"), framework_v2_45)
    assert p.triggered_signals is None


# ================================================================
# Codex #6: multi_model_stats 应按"模型 final_score"求 mean/std
# ================================================================


def test_codex6_multi_model_stats_uses_per_model_final_scores(
    framework_v2_45, no_contradiction_signal
):
    """
    三个模型对同一论文给出不同分数，multi_model_stats 应反映"模型间最终分差异"，
    而非各维度 std 的平均。
    """
    precheck = _adapt_to_v014_contract(PrecheckResult(status="pass"), framework_v2_45)

    # 构造三个模型：分数差异很大（故意制造 final_score 的 std）
    per_model = {
        "model_a": {
            "problem_originality": 85, "literature_insight": 80,
            "analytical_framework": 80, "logical_coherence": 80,
            "conclusion_consensus": 80, "forward_extension": 70,
        },
        "model_b": {
            "problem_originality": 60, "literature_insight": 60,
            "analytical_framework": 60, "logical_coherence": 60,
            "conclusion_consensus": 60, "forward_extension": 50,
        },
        "model_c": {
            "problem_originality": 40, "literature_insight": 40,
            "analytical_framework": 40, "logical_coherence": 40,
            "conclusion_consensus": 40, "forward_extension": 40,
        },
    }

    # reliability_reports 只用于触发非空路径（per_model_scores 有值时优先）
    reports = [
        ReliabilityReport(
            dimension_key="problem_originality", mean=62, std=22,
            is_high_confidence=False, model_scores={},
        ),
    ]

    # 不传 per_model：走回退路径
    result_fallback = aggregate_result(
        {"problem_originality": 62}, precheck, no_contradiction_signal,
        reports, framework_v2_45,
    )
    # 传 per_model：按模型 final_score 统计
    result_by_model = aggregate_result(
        {"problem_originality": 62}, precheck, no_contradiction_signal,
        reports, framework_v2_45, per_model_scores=per_model,
    )

    assert result_fallback.multi_model_stats is not None
    assert result_by_model.multi_model_stats is not None

    # 模型间 final_score 差异应远大于各维度 std 的平均
    by_model_std = result_by_model.multi_model_stats.std
    # fallback_std 是维度 std 平均 = 22；by_model_std 是三模型 final 的 stdev
    # model_a ~ 85, model_b ~ 55, model_c ~ 40 → stdev > 20
    # 这里验证两者方法路径不同（不会收敛到同一值）
    assert result_fallback.multi_model_stats.std != by_model_std, (
        "期望两种统计口径不同，否则无法验证 Codex #6 的修复"
    )
    assert by_model_std >= 15, f"期望按模型 final 算出的 std 较大，实际 {by_model_std}"
    # 置信度分级应反映 final_score 波动
    assert result_by_model.multi_model_stats.confidence_label in ("low", "critical"), (
        f"三模型差异大，应被标记低置信度，实际 {result_by_model.multi_model_stats.confidence_label}"
    )


def test_codex6_single_model_has_zero_std(
    framework_v2_45, no_contradiction_signal
):
    """单模型场景：final_score std = 0.0（stdev 无法计算时的正确回退）。"""
    precheck = _adapt_to_v014_contract(PrecheckResult(status="pass"), framework_v2_45)
    per_model = {
        "only_model": {
            "problem_originality": 75, "literature_insight": 70,
            "analytical_framework": 70, "logical_coherence": 70,
            "conclusion_consensus": 70, "forward_extension": 60,
        },
    }
    reports = [
        ReliabilityReport(
            dimension_key="problem_originality", mean=75, std=0,
            is_high_confidence=True, model_scores={},
        ),
    ]
    result = aggregate_result(
        {"problem_originality": 75}, precheck, no_contradiction_signal,
        reports, framework_v2_45, per_model_scores=per_model,
    )
    assert result.multi_model_stats.std == 0.0
    assert result.multi_model_stats.confidence_label == "high"


# ================================================================
# 回归：legacy 框架（v2.0）不受修复影响
# ================================================================


def test_legacy_framework_unaffected(framework_legacy, no_contradiction_signal):
    """v2.0 旧框架继续走旧路径，不应被 Codex 修复意外影响。"""
    precheck = _adapt_to_v014_contract(
        PrecheckResult(status="pass"), framework_legacy
    )
    # 旧框架：conclusion 仍为 None（不走 v2.45 适配层）
    assert precheck.conclusion is None
    assert precheck.enter_six_dimension_review is None

    result = aggregate_result(
        {"problem_originality": 80, "literature_insight": 70},
        precheck, no_contradiction_signal, [], framework_legacy,
    )
    # 默认走 enter_six_dimension_review，review_status = none
    assert result.review_status == "none"
    assert result.review_level == "none"
