from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.api.auth.account import invalidate_user_sessions, revoke_user_api_keys
from src.api.auth.dependencies import require_roles
from src.api.auth.tokens import create_one_time_token
from src.api.schemas.users import (
    InvitationCreateRequest,
    InvitationListResponse,
    InvitationResponse,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
    default_expiration,
)
from src.core.audit import record_audit_log
from src.core.config import settings
from src.core.database import get_db
from src.core.email import queue_email
from src.core.time import utc_now
from src.models.editorial import (
    EmailDelivery,
    EditorialSubmission,
    EditorialUnit,
    EditorialUnitMembership,
)
from src.models.review import ExpertReview
from src.models.user import Invitation, PasswordResetToken, User

router = APIRouter()

TERMINAL_SUBMISSION_STATES = {
    "completed",
    "sent_for_external_review",
    "closed",
    "rejected",
}
TERMINAL_REVIEW_STATES = {"submitted", "completed", "returned"}


def _user_response(user: User) -> UserResponse:
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
        auth_method=None,
    )


def _invitation_status(invitation: Invitation) -> str:
    if invitation.revoked_at is not None:
        return "revoked"
    if invitation.is_used:
        return "used"
    if invitation.expires_at <= utc_now():
        return "expired"
    return "pending"


def _invitation_response(
    invitation: Invitation,
    *,
    raw_token: str | None = None,
    email_status: str = "unknown",
) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        token=raw_token if settings.app_env != "production" else None,
        email_status=email_status,
        status=_invitation_status(invitation),
        unit_ids=invitation.unit_ids or [],
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
    )


def _active_responsibilities(db: Session, user: User) -> dict[str, int]:
    submissions = (
        db.query(EditorialSubmission)
        .filter(
            EditorialSubmission.responsible_editor_id == user.id,
            EditorialSubmission.status.notin_(TERMINAL_SUBMISSION_STATES),
        )
        .count()
    )
    reviews = (
        db.query(ExpertReview)
        .filter(
            ExpertReview.expert_id == user.id,
            ExpertReview.status.notin_(TERMINAL_REVIEW_STATES),
        )
        .count()
    )
    memberships = (
        db.query(EditorialUnitMembership)
        .filter(
            EditorialUnitMembership.user_id == user.id,
            EditorialUnitMembership.is_active.is_(True),
        )
        .count()
    )
    return {
        "负责稿件": submissions,
        "待办复核": reviews,
        "有效编辑单元成员关系": memberships,
    }


def _ensure_no_active_responsibilities(db: Session, user: User) -> None:
    counts = _active_responsibilities(db, user)
    active = {label: count for label, count in counts.items() if count}
    if active:
        details = "，".join(f"{label} {count} 项" for label, count in active.items())
        raise HTTPException(
            status_code=409,
            detail=f"请先转移或完成该用户的职责：{details}",
        )


def _ensure_admin_safeguards(
    db: Session,
    current_user: User,
    target: User,
    *,
    new_role: str | None,
    new_active: bool | None,
) -> None:
    removes_admin = target.role == "admin" and (
        new_role not in (None, "admin") or new_active is False
    )
    if target.id == current_user.id and (
        new_active is False or new_role not in (None, "admin")
    ):
        raise HTTPException(status_code=409, detail="管理员不能停用或降级自己")
    if removes_admin:
        other_admins = (
            db.query(User)
            .filter(
                User.role == "admin",
                User.is_active.is_(True),
                User.id != target.id,
            )
            .count()
        )
        if other_admins == 0:
            raise HTTPException(status_code=409, detail="不能移除最后一个有效管理员")


@router.get("", response_model=UserListResponse)
def list_users(
    q: str | None = Query(default=None, max_length=255),
    role: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> UserListResponse:
    query = db.query(User)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(User.email.ilike(pattern), User.display_name.ilike(pattern))
        )
    if role:
        query = query.filter(User.role == role)
    if active is not None:
        query = query.filter(User.is_active.is_(active))
    users = query.order_by(User.created_at.asc()).all()
    return UserListResponse(items=[_user_response(user) for user in users])


@router.get("/experts", response_model=UserListResponse)
def list_experts(
    _: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> UserListResponse:
    users = (
        db.query(User)
        .filter(User.role == "expert", User.is_active.is_(True))
        .order_by(User.created_at.asc())
        .all()
    )
    return UserListResponse(items=[_user_response(user) for user in users])


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> UserResponse:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="未找到用户")
    if payload.role is None and payload.is_active is None:
        raise HTTPException(status_code=400, detail="没有需要更新的用户字段")
    _ensure_admin_safeguards(
        db,
        current_user,
        target,
        new_role=payload.role,
        new_active=payload.is_active,
    )
    if payload.is_active is False or (
        payload.role is not None and payload.role != target.role
    ):
        _ensure_no_active_responsibilities(db, target)
    changes: dict[str, object] = {}
    if payload.role is not None and payload.role != target.role:
        changes["role_from"] = target.role
        changes["role_to"] = payload.role
        target.role = payload.role
        invalidate_user_sessions(target)
        changes["api_keys_revoked"] = revoke_user_api_keys(db, target.id)
    if payload.is_active is not None and payload.is_active != target.is_active:
        changes["active_from"] = target.is_active
        changes["active_to"] = payload.is_active
        target.is_active = payload.is_active
        if not payload.is_active:
            invalidate_user_sessions(target)
            changes["api_keys_revoked"] = revoke_user_api_keys(db, target.id)
    db.add(target)
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="user",
        object_id=target.id,
        action="user_updated",
        result="success",
        details=changes,
    )
    queue_email(
        db,
        idempotency_key=(
            f"account-status-changed:{target.id}:"
            f"{utc_now().isoformat(timespec='microseconds')}"
        ),
        event_type="account_status_changed",
        recipient_email=target.email,
        object_type="user",
        object_id=target.id,
    )
    return _user_response(target)


@router.post("/{user_id}/password-reset", status_code=status.HTTP_202_ACCEPTED)
def admin_send_password_reset(
    user_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="未找到有效用户")
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
    user.password_reset_required = True
    invalidate_user_sessions(user)
    revoked = revoke_user_api_keys(db, user.id)
    db.add_all([user, token])
    db.commit()
    db.refresh(token)
    queue_email(
        db,
        idempotency_key=f"admin-password-reset:{token.id}",
        event_type="password_reset_requested",
        recipient_email=user.email,
        object_type="password_reset",
        object_id=token.id,
        template_data={"token": raw_token},
    )
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="user",
        object_id=user.id,
        action="admin_password_reset_sent",
        result="success",
        details={"api_keys_revoked": revoked},
    )
    return {"message": "密码重置邮件已进入发送队列"}


@router.post("/{user_id}/api-keys/revoke", status_code=status.HTTP_204_NO_CONTENT)
def admin_revoke_api_keys(
    user_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="未找到用户")
    count = revoke_user_api_keys(db, user.id)
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="user",
        object_id=user.id,
        action="admin_api_keys_revoked",
        result="success",
        details={"count": count},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/invitations", response_model=InvitationListResponse)
def list_invitations(
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> InvitationListResponse:
    rows = db.query(Invitation).order_by(Invitation.created_at.desc()).all()
    return InvitationListResponse(items=[_invitation_response(row) for row in rows])


@router.post(
    "/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    payload: InvitationCreateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> InvitationResponse:
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status_code=409, detail="该邮箱的用户已经存在")
    existing = (
        db.query(Invitation)
        .filter(
            Invitation.email == email,
            Invitation.is_used.is_(False),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > utc_now(),
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="该邮箱已经存在有效邀请")
    unit_ids = payload.unit_ids if payload.role == "editor" else []
    for uid in unit_ids:
        if db.get(EditorialUnit, uid) is None:
            raise HTTPException(status_code=422, detail=f"编辑单元不存在：{uid}")
    raw_token, token_hash = create_one_time_token()
    invitation = Invitation(
        email=email,
        role=payload.role,
        token_hash=token_hash,
        invited_by=current_user.id,
        expires_at=default_expiration(payload.expires_in_days),
        sent_at=utc_now(),
        unit_ids=unit_ids,
        membership_role=payload.membership_role if payload.role == "editor" else "editor",
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    delivery = queue_email(
        db,
        idempotency_key=f"invitation-created:{invitation.id}:{invitation.sent_at}",
        event_type="invitation_created",
        recipient_email=invitation.email,
        object_type="invitation",
        object_id=invitation.id,
        template_data={
            "token": raw_token,
            "expires_at": invitation.expires_at.isoformat(timespec="minutes"),
        },
    )
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="invitation",
        object_id=invitation.id,
        action="invitation_created",
        result="success",
    )
    return _invitation_response(
        invitation,
        raw_token=raw_token,
        email_status=delivery.status,
    )


@router.post(
    "/invitations/{invitation_id}/resend",
    response_model=InvitationResponse,
)
def resend_invitation(
    invitation_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> InvitationResponse:
    invitation = db.get(Invitation, invitation_id)
    if invitation is None or invitation.is_used or invitation.revoked_at is not None:
        raise HTTPException(status_code=409, detail="该邀请不能重新发送")
    raw_token, token_hash = create_one_time_token()
    invitation.token = None
    invitation.token_hash = token_hash
    invitation.expires_at = utc_now() + timedelta(days=settings.invitation_ttl_days)
    invitation.sent_at = utc_now()
    db.add(invitation)
    db.commit()
    delivery = queue_email(
        db,
        idempotency_key=f"invitation-resent:{invitation.id}:{invitation.sent_at}",
        event_type="invitation_created",
        recipient_email=invitation.email,
        object_type="invitation",
        object_id=invitation.id,
        template_data={
            "token": raw_token,
            "expires_at": invitation.expires_at.isoformat(timespec="minutes"),
        },
    )
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="invitation",
        object_id=invitation.id,
        action="invitation_resent",
        result="success",
    )
    return _invitation_response(
        invitation,
        raw_token=raw_token,
        email_status=delivery.status,
    )


@router.delete(
    "/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_invitation(
    invitation_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> Response:
    invitation = db.get(Invitation, invitation_id)
    if invitation is None:
        raise HTTPException(status_code=404, detail="未找到邀请")
    if invitation.is_used:
        raise HTTPException(status_code=409, detail="已经使用的邀请不能撤销")
    invitation.revoked_at = utc_now()
    invitation.token = None
    invitation.token_hash = None
    db.add(invitation)
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="invitation",
        object_id=invitation.id,
        action="invitation_revoked",
        result="success",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/email-deliveries")
def list_email_deliveries(
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    rows = (
        db.query(EmailDelivery)
        .order_by(EmailDelivery.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "object_type": row.object_type,
                "object_id": row.object_id,
                "status": row.status,
                "attempt_count": row.attempt_count,
                "last_error": row.last_error,
                "next_attempt_at": row.next_attempt_at,
                "accepted_at": row.accepted_at,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.post("/email-deliveries/{delivery_id}/retry")
def retry_email_delivery(
    delivery_id: str,
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    delivery = db.get(EmailDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="未找到邮件投递记录")
    if delivery.status == "accepted":
        raise HTTPException(status_code=409, detail="邮件已经被 SMTP 接受")
    delivery.status = "queued" if settings.email_enabled else "disabled"
    delivery.last_error = None
    delivery.next_attempt_at = None
    db.commit()
    if settings.email_enabled:
        from src.tasks.email_task import dispatch_email_delivery

        dispatch_email_delivery(delivery.id)
    return {"id": delivery.id, "status": delivery.status}
