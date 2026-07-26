from fastapi import Request

from src.models.user import User

SESSION_USER_ID_KEY = "user_id"
SESSION_AUTH_METHOD_KEY = "auth_method"
SESSION_VERSION_KEY = "session_version"
MFA_PENDING_USER_ID_KEY = "mfa_pending_user_id"


def login_user(request: Request, user: User) -> None:
    request.session.clear()
    request.session[SESSION_USER_ID_KEY] = user.id
    request.session[SESSION_AUTH_METHOD_KEY] = "session"
    request.session[SESSION_VERSION_KEY] = user.session_version


def begin_mfa_challenge(request: Request, user: User) -> None:
    request.session.clear()
    request.session[MFA_PENDING_USER_ID_KEY] = user.id


def logout_user(request: Request) -> None:
    request.session.clear()
