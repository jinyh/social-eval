from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from src.core.time import utc_now


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    display_name: str | None = None
    affiliation: str | None = None
    is_active: bool
    email_verified_at: datetime | None = None
    created_at: datetime
    last_login_at: datetime | None = None
    password_changed_at: datetime | None = None
    password_reset_required: bool = False
    mfa_enabled: bool = False
    auth_method: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    items: list[UserResponse]


class InvitationCreateRequest(BaseModel):
    email: str
    role: str = Field(pattern="^(editor|expert|admin)$")
    expires_in_days: int = Field(default=7, ge=1, le=30)
    unit_ids: list[str] = Field(default_factory=list)
    membership_role: str = Field(default="editor", pattern="^(editor|unit_admin)$")


class InvitationResponse(BaseModel):
    id: str
    email: str
    role: str
    token: str | None = None
    email_status: str
    status: str = "pending"
    unit_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime


class UserUpdateRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(submitter|editor|expert|admin)$")
    is_active: bool | None = None


class InvitationListResponse(BaseModel):
    items: list[InvitationResponse]


def default_expiration(days: int) -> datetime:
    return utc_now() + timedelta(days=days)
