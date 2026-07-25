from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from src.editorial.ai_calls import generate_json_with_audit
from src.evaluation.position.workflow import (
    MODELS,
    aggregate_final_assessment,
    apply_node_validation_to_assessment,
    build_light_round2_prompt,
    build_round1_prompt,
    build_round2_prompt,
    decide_round2_policy,
    discipline_hint_from_meta,
    enforce_light_round2_axis_agreement,
    format_retrieved_nodes_for_prompt,
    load_law_ontology,
    query_text_for_retrieval,
)
from src.evaluation.providers.base import BaseProvider
from src.knowledge.node_retrieval import retrieve_nodes
from src.models.editorial import PositionAssessment


async def run_position_assessment(
    db: Session,
    *,
    submission_id: str,
    task_id: str,
    providers: list[BaseProvider],
    title: str,
    journal_name: str,
    anonymized_text: str,
) -> PositionAssessment:
    """把既有五轴两模型流程接入编辑投稿，并持久化原始调用。"""

    provider_map = {provider.model_name: provider for provider in providers}
    missing = [model for model in MODELS if model not in provider_map]
    if missing:
        raise ValueError(
            "Position assessment requires providers: " + ", ".join(missing)
        )
    ontology = load_law_ontology(Path("knowledge/law_ontology.json"))
    meta = {"title": title, "journal": journal_name, "discipline": "法学"}
    nodes = retrieve_nodes(
        query_text_for_retrieval(meta, anonymized_text),
        ontology,
        discipline_hint=discipline_hint_from_meta(meta),
        top_k=20,
    )
    node_text = format_retrieved_nodes_for_prompt(nodes)
    prompt = build_round1_prompt(
        meta,
        anonymized_text,
        "",
        node_candidates_text=node_text,
    )

    async def r1(model: str) -> tuple[str, dict]:
        payload = await generate_json_with_audit(
            db,
            task_id=task_id,
            provider=provider_map[model],
            call_type="position_r1",
            prompt=prompt,
            dimension_key="__position__",
            round_number=1,
        )
        return model, apply_node_validation_to_assessment(
            payload,
            ontology=ontology,
            retrieved_nodes=nodes,
            paper_title=title,
            paper_text=anonymized_text,
        )

    r1_outputs = dict([await r1(model) for model in MODELS])
    r1_result = {"models": r1_outputs}
    r2_policy = decide_round2_policy(r1_result)
    final_outputs = r1_outputs
    if r2_policy["mode"] != "skip":
        prompts = {}
        for index, model in enumerate(MODELS):
            other = MODELS[1 - index]
            if r2_policy["mode"] == "light":
                prompts[model] = build_light_round2_prompt(
                    meta,
                    "",
                    r1_outputs[model],
                    r1_outputs[other],
                    model,
                    other,
                    node_candidates_text=node_text,
                )
            else:
                prompts[model] = build_round2_prompt(
                    meta,
                    anonymized_text,
                    "",
                    r1_outputs[model],
                    r1_outputs[other],
                    model,
                    other,
                    node_candidates_text=node_text,
                )

        async def r2(model: str) -> tuple[str, dict]:
            payload = await generate_json_with_audit(
                db,
                task_id=task_id,
                provider=provider_map[model],
                call_type="position_r2",
                prompt=prompts[model],
                dimension_key="__position__",
                round_number=2,
            )
            validated = apply_node_validation_to_assessment(
                payload,
                ontology=ontology,
                retrieved_nodes=nodes,
                paper_title=title,
                paper_text=anonymized_text,
            )
            if r2_policy["mode"] == "light":
                validated = enforce_light_round2_axis_agreement(
                    validated,
                    r1_result=r1_result,
                    model_name=model,
                )
            return model, validated

        final_outputs = dict([await r2(model) for model in MODELS])

    result = {
        "round1": r1_result,
        "round2_policy": r2_policy,
        "final": aggregate_final_assessment(final_outputs),
    }
    record = PositionAssessment(
        submission_id=submission_id,
        version=1,
        status="completed",
        result_data=result,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
