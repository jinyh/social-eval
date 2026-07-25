from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.auth.dependencies import require_roles
from src.api.schemas.users import (
    InvitationCreateRequest,
    InvitationResponse,
    UserListResponse,
    UserResponse,
    default_expiration,
)
from src.core.database import get_db
from src.core.config import settings
from src.core.email import queue_email
from src.models.editorial import EmailDelivery
from src.models.user import Invitation, User

router = APIRouter()


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        auth_method=None,
    )


@router.get("", response_model=UserListResponse)
def list_users(
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> UserListResponse:
    users = db.query(User).order_by(User.created_at.asc()).all()
    return UserListResponse(items=[_user_response(user) for user in users])


@router.get("/experts", response_model=UserListResponse)
def list_experts(
    _: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> UserListResponse:
    users = (
        db.query(User)
        .filter(User.role == "expert")
        .order_by(User.created_at.asc())
        .all()
    )
    return UserListResponse(items=[_user_response(user) for user in users])


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
    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱的用户已经存在",
        )
    existing_invitation = (
        db.query(Invitation)
        .filter(Invitation.email == payload.email, Invitation.is_used.is_(False))
        .first()
    )
    if existing_invitation is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已经存在有效邀请",
        )

    invitation = Invitation(
        email=payload.email,
        role=payload.role,
        token=secrets.token_urlsafe(32),
        invited_by=current_user.id,
        expires_at=default_expiration(payload.expires_in_days),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    delivery = queue_email(
        db,
        idempotency_key=f"invitation-created:{invitation.id}",
        event_type="invitation_created",
        recipient_email=invitation.email,
        object_type="invitation",
        object_id=invitation.id,
        template_data={
            "token": invitation.token,
            "expires_at": invitation.expires_at.isoformat(timespec="minutes"),
        },
    )
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        token=None if settings.email_enabled else invitation.token,
        email_status=delivery.status,
        expires_at=invitation.expires_at,
    )


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
