from __future__ import annotations


def build_public_report(internal_report: dict) -> dict:
    public_dimensions = []
    for dimension in internal_report["dimensions"]:
        public_dimensions.append(
            {
                "key": dimension["key"],
                "name_zh": dimension["name_zh"],
                "name_en": dimension["name_en"],
                "weight": dimension["weight"],
                "summary": dimension.get("summary"),
                "ai": {
                    "mean_score": dimension["ai"]["mean_score"],
                    "std_score": dimension["ai"]["std_score"],
                    "is_high_confidence": dimension["ai"]["is_high_confidence"],
                },
            }
        )

    expert_summaries = []
    for review in internal_report["expert_reviews"]:
        expert_summaries.append(
            {
                "review_id": review["review_id"],
                "status": review["status"],
                "comments": [
                    {
                        "dimension_key": comment["dimension_key"],
                        "expert_score": comment["expert_score"],
                        "reason": comment["reason"],
                    }
                    for comment in review["comments"]
                ],
            }
        )

    return {
        "report_type": "public",
        "paper_id": internal_report["paper_id"],
        "task_id": internal_report["task_id"],
        "framework": internal_report.get("framework"),
        "model_count": len(internal_report.get("models", [])),
        "paper_title": internal_report["paper_title"],
        "title": internal_report["paper_title"],
        "ai_weighted_total": internal_report.get("ai_weighted_total"),
        "expert_adjusted_total": internal_report.get("expert_adjusted_total"),
        "weighted_total": internal_report["weighted_total"],
        "conclusion": internal_report.get("conclusion"),
        "expert_review_required": internal_report.get("expert_review_required", False),
        "radar_chart": internal_report["radar_chart"],
        "dimensions": public_dimensions,
        "expert_reviews": expert_summaries,
        "expert_conclusion": _build_expert_conclusion(expert_summaries),
    }


def _build_expert_conclusion(expert_summaries: list[dict]) -> str | None:
    reasons = [
        comment["reason"]
        for review in expert_summaries
        if review.get("status") == "submitted"
        for comment in review.get("comments", [])
        if comment.get("reason")
    ]
    if not reasons:
        return None
    return "；".join(reasons[:3])
