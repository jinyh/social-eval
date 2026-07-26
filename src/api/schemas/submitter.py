from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SubmitterJournal(BaseModel):
    unit_id: str
    journal_name: str
    unit_name: str
    accepted_scope: list[str]
    column_positioning: list[str]
    article_types: list[str]
    special_notes: str


class SubmitterSubmission(BaseModel):
    id: str
    paper_id: str
    unit_id: str
    journal_name: str
    unit_name: str
    title: str
    status: str
    status_label: str
    created_at: datetime
    updated_at: datetime
    report_released: bool
    public_decision: str | None = None
    author_message: str | None = None
    withdrawal_status: str | None = None


class WithdrawalRequestCreate(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)
