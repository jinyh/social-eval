from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class AcceptInvitationRequest(BaseModel):
    token: str
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class LoginResponse(BaseModel):
    status: Literal["authenticated", "mfa_required", "mfa_setup_required"]
    user: "UserResponse | None" = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)
    revoke_api_keys: bool = True


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=12, max_length=128)


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MfaRecoveryRegenerateRequest(MfaCodeRequest):
    password: str


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    qr_svg: str


class MfaConfirmResponse(LoginResponse):
    recovery_codes: list[str]


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    expires_in_days: int = Field(default=90, ge=1, le=90)


class ApiKeyResponse(BaseModel):
    id: str
    name: str | None
    key_prefix: str
    api_key: str
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyMetadata(BaseModel):
    id: str
    name: str | None
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


from src.api.schemas.users import UserResponse  # noqa: E402

LoginResponse.model_rebuild()
