from __future__ import annotations

from datetime import timedelta
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from src.api.auth.account import invalidate_user_sessions, revoke_user_api_keys
from src.api.auth.api_key import create_api_key
from src.api.auth.dependencies import get_current_user
from src.api.auth.mfa import (
    consume_recovery_code,
    create_totp_setup,
    replace_recovery_codes,
    verify_totp,
)
from src.api.auth.password import (
    hash_password,
    verify_and_update_password,
    verify_password,
)
from src.api.auth.session import (
    MFA_PENDING_USER_ID_KEY,
    begin_mfa_challenge,
    login_user,
    logout_user,
)
from src.api.auth.tokens import create_one_time_token, hash_one_time_token
from src.api.schemas.auth import (
    AcceptInvitationRequest,
    ApiKeyCreateRequest,
    ApiKeyMetadata,
    ApiKeyResponse,
    ChangePasswordRequest,
    EmailVerificationRequest,
    EmailVerificationResendRequest,
    LoginRequest,
    LoginResponse,
    MfaCodeRequest,
    MfaConfirmResponse,
    MfaRecoveryRegenerateRequest,
    MfaSetupResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegistrationRequest,
    RegistrationResponse,
)
from src.api.schemas.users import UserResponse
from src.core.audit import record_audit_log
from src.core.config import settings
from src.core.database import get_db
from src.core.email import queue_email
from src.core.login_guard import (
    LoginGuardUnavailable,
    clear_failed_logins,
    register_failed_login,
    register_security_failure,
)
from src.core.time import utc_now
from src.models.api_key import ApiKey
from src.models.editorial import EditorialUnit, EditorialUnitMembership
from src.models.user import (
    EmailVerificationToken,
    Invitation,
    PasswordResetToken,
    User,
)

router = APIRouter()


def _build_user_response(user: User, *, auth_method: str | None = None) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
        affiliation=user.affiliation,
        is_active=user.is_active,
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        password_changed_at=user.password_changed_at,
        password_reset_required=user.password_reset_required,
        mfa_enabled=user.mfa_enabled_at is not None,
        auth_method=auth_method,
    )


def _normalized_email(email: str) -> str:
    value = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise HTTPException(status_code=422, detail="请输入有效的电子邮箱")
    return value


def _queue_verification(db: Session, user: User) -> str:
    now = utc_now()
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user.id,
        EmailVerificationToken.used_at.is_(None),
    ).update({"used_at": now})
    raw_token, token_hash = create_one_time_token()
    token = EmailVerificationToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(seconds=settings.email_verification_ttl_seconds),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    queue_email(
        db,
        idempotency_key=f"email-verification:{token.id}",
        event_type="email_verification_requested",
        recipient_email=user.email,
        object_type="email_verification",
        object_id=token.id,
        template_data={"token": raw_token},
    )
    return raw_token


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def register(
    payload: RegistrationRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> RegistrationResponse:
    if payload.website:
        return RegistrationResponse(message="请检查邮箱并完成账户验证")
    if settings.app_env == "production" and not settings.email_enabled:
        raise HTTPException(status_code=503, detail="账户注册暂不可用，请稍后再试")
    email = _normalized_email(payload.email)
    client_ip = request.client.host if request.client else "unknown"
    _security_limit("registration", f"{client_ip}|{email}")
    existing = db.query(User).filter(User.email == email).first()
    verification_url = None
    if existing is None:
        user = User(
            email=email,
            display_name=payload.display_name.strip(),
            affiliation=(payload.affiliation or "").strip() or None,
            hashed_password=hash_password(payload.password),
            role="submitter",
            is_active=False,
            password_changed_at=utc_now(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        raw_token = _queue_verification(db, user)
        record_audit_log(
            db,
            actor_id=user.id,
            object_type="user",
            object_id=user.id,
            action="self_registration_created",
            result="pending_verification",
        )
        if settings.app_env != "production":
            verification_url = (
                f"{settings.public_base_url.rstrip('/')}/verify-email#token={raw_token}"
            )
    return RegistrationResponse(
        message="请检查邮箱并完成账户验证",
        verification_url=verification_url,
    )


@router.post("/email-verification/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_email_verification(
    payload: EmailVerificationRequest,
    db: Session = Depends(get_db),
) -> Response:
    token_hash = hash_one_time_token(payload.token)
    token = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.token_hash == token_hash)
        .first()
    )
    if token is None or token.used_at is not None or token.expires_at <= utc_now():
        _security_limit("email-verification-confirm", token_hash)
        raise HTTPException(status_code=400, detail="邮箱验证链接无效或已经过期")
    user = db.get(User, token.user_id)
    if user is None or user.role != "submitter":
        raise HTTPException(status_code=400, detail="邮箱验证链接无效或已经过期")
    token.used_at = utc_now()
    user.email_verified_at = utc_now()
    user.is_active = True
    db.add_all([token, user])
    db.commit()
    record_audit_log(
        db,
        actor_id=user.id,
        object_type="user",
        object_id=user.id,
        action="email_verified",
        result="success",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/email-verification/resend",
    response_model=RegistrationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resend_email_verification(
    payload: EmailVerificationResendRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> RegistrationResponse:
    if settings.app_env == "production" and not settings.email_enabled:
        raise HTTPException(status_code=503, detail="账户注册暂不可用，请稍后再试")
    email = _normalized_email(payload.email)
    client_ip = request.client.host if request.client else "unknown"
    _security_limit("registration-resend", f"{client_ip}|{email}")
    user = (
        db.query(User)
        .filter(
            User.email == email,
            User.role == "submitter",
            User.email_verified_at.is_(None),
        )
        .first()
    )
    verification_url = None
    if user is not None:
        latest = (
            db.query(EmailVerificationToken)
            .filter(EmailVerificationToken.user_id == user.id)
            .order_by(EmailVerificationToken.created_at.desc())
            .first()
        )
        if (
            latest is None
            or (utc_now() - latest.created_at).total_seconds()
            >= settings.registration_resend_cooldown_seconds
        ):
            raw_token = _queue_verification(db, user)
            if settings.app_env != "production":
                verification_url = (
                    f"{settings.public_base_url.rstrip('/')}"
                    f"/verify-email#token={raw_token}"
                )
    return RegistrationResponse(
        message="如果该邮箱存在待验证账户，系统将重新发送验证邮件",
        verification_url=verification_url,
    )


def _security_limit(scope: str, identity: str) -> None:
    if settings.app_env != "production":
        return
    try:
        attempts, retry_after = register_security_failure(scope, identity)
    except LoginGuardUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if attempts >= settings.security_max_attempts:
        raise HTTPException(
            status_code=429,
            detail=f"安全校验失败次数过多，请在 {retry_after} 秒后重试",
            headers={"Retry-After": str(retry_after)},
        )


def _pending_mfa_user(request: Request, db: Session) -> User:
    user_id = request.session.get(MFA_PENDING_USER_ID_KEY)
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="双因素认证会话已失效")
    return user


@router.post("/login", response_model=UserResponse | LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> UserResponse | LoginResponse:
    client_ip = request.client.host if request.client else "unknown"
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    valid = False
    updated_hash: str | None = None
    if user is not None:
        valid, updated_hash = verify_and_update_password(
            payload.password, user.hashed_password
        )
    if user is None or not valid:
        if settings.app_env == "production":
            try:
                attempts, retry_after = register_failed_login(client_ip, payload.email)
            except LoginGuardUnavailable as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            if attempts >= settings.login_max_attempts:
                raise HTTPException(
                    status_code=429,
                    detail=f"登录失败次数过多，请在 {retry_after} 秒后重试",
                    headers={"Retry-After": str(retry_after)},
                )
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if user.email_verified_at is None and user.role == "submitter":
        raise HTTPException(status_code=403, detail="请先完成邮箱验证")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="用户账户尚未启用")
    if user.password_reset_required:
        raise HTTPException(
            status_code=403,
            detail="管理员已要求重置密码，请使用邮件中的重置链接",
        )
    if settings.app_env == "production":
        try:
            clear_failed_logins(client_ip, payload.email)
        except LoginGuardUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    if updated_hash:
        user.hashed_password = updated_hash
    user.last_login_at = utc_now()
    db.add(user)
    db.commit()
    admin_requires_mfa = user.role == "admin" and settings.admin_mfa_required
    if admin_requires_mfa:
        begin_mfa_challenge(request, user)
        return LoginResponse(
            status=(
                "mfa_required"
                if user.mfa_enabled_at is not None
                else "mfa_setup_required"
            )
        )
    login_user(request, user)
    return _build_user_response(user, auth_method="session")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    _: User = Depends(get_current_user),
) -> Response:
    logout_user(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return _build_user_response(
        current_user,
        auth_method=getattr(request.state, "auth_method", None),
    )


@router.post("/password/change", response_model=UserResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    if not verify_password(payload.current_password, current_user.hashed_password):
        _security_limit("password-change", current_user.id)
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if verify_password(payload.new_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    current_user.hashed_password = hash_password(payload.new_password)
    current_user.password_changed_at = utc_now()
    current_user.password_reset_required = False
    invalidate_user_sessions(current_user)
    revoked = (
        revoke_user_api_keys(db, current_user.id) if payload.revoke_api_keys else 0
    )
    db.add(current_user)
    db.commit()
    login_user(request, current_user)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="user",
        object_id=current_user.id,
        action="password_changed",
        result="success",
        details={"api_keys_revoked": revoked},
    )
    queue_email(
        db,
        idempotency_key=(
            f"password-changed:{current_user.id}:"
            f"{current_user.password_changed_at.isoformat()}"
        ),
        event_type="password_changed",
        recipient_email=current_user.email,
        object_type="user",
        object_id=current_user.id,
    )
    return _build_user_response(current_user, auth_method="session")


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    client_ip = request.client.host if request.client else "unknown"
    _security_limit(
        "password-reset-request",
        f"{client_ip}|{payload.email.strip().lower()}",
    )
    user = (
        db.query(User)
        .filter(User.email == payload.email.strip().lower(), User.is_active.is_(True))
        .first()
    )
    if user is not None:
        now = utc_now()
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).update({"used_at": now})
        raw_token, token_hash = create_one_time_token()
        token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=now + timedelta(seconds=settings.password_reset_ttl_seconds),
        )
        db.add(token)
        db.commit()
        db.refresh(token)
        queue_email(
            db,
            idempotency_key=f"password-reset-requested:{token.id}",
            event_type="password_reset_requested",
            recipient_email=user.email,
            object_type="password_reset",
            object_id=token.id,
            template_data={"token": raw_token},
        )
    return {"message": "如果该邮箱存在有效账户，系统将发送密码重置邮件"}


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    db: Session = Depends(get_db),
) -> Response:
    token_hash = hash_one_time_token(payload.token)
    token = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )
    if token is None or token.used_at is not None or token.expires_at <= utc_now():
        _security_limit("password-reset-confirm", token_hash)
        raise HTTPException(status_code=400, detail="密码重置链接无效或已经过期")
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="密码重置链接无效或已经过期")
    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = utc_now()
    user.password_reset_required = False
    invalidate_user_sessions(user)
    revoked = revoke_user_api_keys(db, user.id)
    token.used_at = utc_now()
    db.add_all([user, token])
    db.commit()
    record_audit_log(
        db,
        actor_id=user.id,
        object_type="user",
        object_id=user.id,
        action="password_reset_completed",
        result="success",
        details={"api_keys_revoked": revoked},
    )
    queue_email(
        db,
        idempotency_key=f"password-reset-completed:{token.id}",
        event_type="password_changed",
        recipient_email=user.email,
        object_type="user",
        object_id=user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def setup_mfa(
    request: Request,
    db: Session = Depends(get_db),
) -> MfaSetupResponse:
    user = _pending_mfa_user(request, db)
    secret, uri, qr_svg = create_totp_setup(user)
    db.add(user)
    db.commit()
    return MfaSetupResponse(
        secret=secret,
        provisioning_uri=uri,
        qr_svg=qr_svg,
    )


@router.post("/mfa/confirm", response_model=MfaConfirmResponse)
def confirm_mfa(
    payload: MfaCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> MfaConfirmResponse:
    user = _pending_mfa_user(request, db)
    if not verify_totp(user, payload.code):
        _security_limit("mfa-confirm", user.id)
        raise HTTPException(status_code=400, detail="动态验证码不正确")
    recovery_codes = replace_recovery_codes(db, user)
    user.mfa_enabled_at = utc_now()
    db.add(user)
    db.commit()
    login_user(request, user)
    record_audit_log(
        db,
        actor_id=user.id,
        object_type="user",
        object_id=user.id,
        action="mfa_enabled",
        result="success",
    )
    return MfaConfirmResponse(
        status="authenticated",
        user=_build_user_response(user, auth_method="session"),
        recovery_codes=recovery_codes,
    )


@router.post("/mfa/verify", response_model=UserResponse)
def verify_mfa_code(
    payload: MfaCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> UserResponse:
    user = _pending_mfa_user(request, db)
    valid_totp = verify_totp(user, payload.code)
    valid_recovery = False
    if not valid_totp:
        valid_recovery = consume_recovery_code(db, user, payload.code)
    if not valid_totp and not valid_recovery:
        _security_limit("mfa-verify", user.id)
        raise HTTPException(status_code=401, detail="动态验证码或恢复码不正确")
    db.commit()
    login_user(request, user)
    if valid_recovery:
        record_audit_log(
            db,
            actor_id=user.id,
            object_type="user",
            object_id=user.id,
            action="mfa_recovery_code_used",
            result="success",
        )
    return _build_user_response(user, auth_method="session")


@router.post("/mfa/recovery-codes/regenerate")
def regenerate_recovery_codes(
    payload: MfaRecoveryRegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, list[str]]:
    if not verify_password(payload.password, current_user.hashed_password):
        _security_limit("mfa-recovery-regenerate", current_user.id)
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if not verify_totp(current_user, payload.code):
        _security_limit("mfa-recovery-regenerate", current_user.id)
        raise HTTPException(status_code=400, detail="动态验证码不正确")
    codes = replace_recovery_codes(db, current_user)
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="user",
        object_id=current_user.id,
        action="mfa_recovery_codes_regenerated",
        result="success",
    )
    return {"recovery_codes": codes}


@router.post(
    "/invitations/accept",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def accept_invitation(
    payload: AcceptInvitationRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    token_hash = hash_one_time_token(payload.token)
    invitation = (
        db.query(Invitation).filter(Invitation.token_hash == token_hash).first()
    )
    if invitation is None:
        invitation = (
            db.query(Invitation).filter(Invitation.token == payload.token).first()
        )
    if invitation is None or invitation.is_used or invitation.revoked_at is not None:
        raise HTTPException(status_code=404, detail="未找到有效邀请")
    if invitation.expires_at < utc_now():
        raise HTTPException(status_code=400, detail="邀请已经过期")
    if db.query(User).filter(User.email == invitation.email).first() is not None:
        raise HTTPException(status_code=409, detail="用户已经存在")
    user = User(
        email=invitation.email.strip().lower(),
        display_name=invitation.display_name,
        affiliation=None,
        hashed_password=hash_password(payload.password),
        role=invitation.role,
        is_active=True,
        password_changed_at=utc_now(),
        email_verified_at=utc_now(),
    )
    invitation.is_used = True
    invitation.token = None
    db.add_all([user, invitation])
    db.flush()  # 让 user.id 可用于建立成员关系
    memberships: list[EditorialUnitMembership] = []
    if invitation.role == "editor":
        membership_role = invitation.membership_role or "editor"
        for uid in invitation.unit_ids or []:
            if db.get(EditorialUnit, uid) is None:
                continue  # 单元已删则跳过，不阻断激活
            memberships.append(
                EditorialUnitMembership(
                    unit_id=uid,
                    user_id=user.id,
                    membership_role=membership_role,
                    is_active=True,
                )
            )
    if memberships:
        db.add_all(memberships)
    db.commit()
    db.refresh(user)
    record_audit_log(
        db,
        actor_id=user.id,
        object_type="user",
        object_id=user.id,
        action="invitation_accepted",
        result="success",
    )
    return _build_user_response(user)


@router.get("/api-keys", response_model=list[ApiKeyMetadata])
def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApiKey]:
    return (
        db.query(ApiKey)
        .filter(ApiKey.user_id == current_user.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


@router.post(
    "/api-keys",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
def issue_api_key(
    payload: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyResponse:
    expires_at = utc_now() + timedelta(days=payload.expires_in_days)
    api_key, raw_key = create_api_key(
        db,
        user_id=current_user.id,
        name=payload.name,
        expires_at=expires_at,
    )
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="api_key",
        object_id=api_key.id,
        action="api_key_created",
        result="success",
    )
    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        api_key=raw_key,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@router.delete("/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    api_key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = (
        db.query(ApiKey)
        .filter(ApiKey.id == api_key_id, ApiKey.user_id == current_user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="未找到 API Key")
    row.is_active = False
    db.add(row)
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="api_key",
        object_id=row.id,
        action="api_key_revoked",
        result="success",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
