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
    users = db.query(User).filter(User.role == "expert").order_by(User.created_at.asc()).all()
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
            detail="User with this email already exists",
        )
    existing_invitation = (
        db.query(Invitation)
        .filter(Invitation.email == payload.email, Invitation.is_used.is_(False))
        .first()
    )
    if existing_invitation is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active invitation already exists",
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
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        token=invitation.token,
        expires_at=invitation.expires_at,
    )
