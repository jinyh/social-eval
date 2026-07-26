from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.core.field_encryption import decrypt_field
from src.models.editorial import EmailDelivery
from src.models.user import EmailVerificationToken, User
from tests.test_api.conftest import create_user


def test_admin_can_invite_user_activate_account_and_login(
    client: TestClient, db_session: Session
) -> None:
    create_user(
        db_session,
        email="admin@example.com",
        role="admin",
        display_name="Admin",
    )

    login_response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )
    assert login_response.status_code == 200

    invite_response = client.post(
        "/api/users/invitations",
        json={"email": "editor@example.com", "role": "editor"},
    )
    assert invite_response.status_code == 201
    token = invite_response.json()["token"]

    activation_response = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": token,
            "display_name": "Editor User",
            "password": "new-password-123",
        },
    )
    assert activation_response.status_code == 201
    assert activation_response.json()["email"] == "editor@example.com"
    assert activation_response.json()["role"] == "editor"

    client.cookies.clear()
    invited_login = client.post(
        "/api/auth/login",
        json={"email": "editor@example.com", "password": "new-password-123"},
    )
    assert invited_login.status_code == 200
    assert invited_login.json()["email"] == "editor@example.com"

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "editor@example.com"
    assert me_response.json()["display_name"] == "Editor User"
    assert me_response.json()["auth_method"] == "session"


def test_api_key_can_access_protected_route(
    client: TestClient, db_session: Session
) -> None:
    create_user(
        db_session,
        email="editor@example.com",
        role="editor",
        display_name="Editor",
    )

    login_response = client.post(
        "/api/auth/login",
        json={"email": "editor@example.com", "password": "secret123"},
    )
    assert login_response.status_code == 200

    api_key_response = client.post(
        "/api/auth/api-keys",
        json={"name": "integration"},
    )
    assert api_key_response.status_code == 201
    raw_api_key = api_key_response.json()["api_key"]

    client.cookies.clear()
    me_response = client.get(
        "/api/auth/me",
        headers={"X-API-Key": raw_api_key},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "editor@example.com"
    assert me_response.json()["auth_method"] == "api_key"


def test_login_rejects_invalid_credentials(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin@example.com", role="admin")

    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_health_endpoint_is_available_without_auth(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_submitter_can_self_register_verify_and_login(
    client: TestClient, db_session: Session
) -> None:
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "AUTHOR@example.com",
            "display_name": "投稿作者",
            "affiliation": "某大学",
            "password": "a-secure-password",
        },
    )
    assert registered.status_code == 202
    user = db_session.query(User).filter(User.email == "author@example.com").one()
    assert user.role == "submitter"
    assert user.is_active is False
    assert user.affiliation == "某大学"
    assert user.email_verified_at is None
    token_row = db_session.query(EmailVerificationToken).one()
    delivery = (
        db_session.query(EmailDelivery)
        .filter(EmailDelivery.event_type == "email_verification_requested")
        .one()
    )
    token = decrypt_field(delivery.template_data["token_encrypted"])
    assert token not in token_row.token_hash

    blocked = client.post(
        "/api/auth/login",
        json={"email": "author@example.com", "password": "a-secure-password"},
    )
    assert blocked.status_code == 403
    assert "邮箱验证" in blocked.json()["detail"]

    verified = client.post(
        "/api/auth/email-verification/confirm",
        json={"token": token},
    )
    assert verified.status_code == 204
    repeated = client.post(
        "/api/auth/email-verification/confirm",
        json={"token": token},
    )
    assert repeated.status_code == 400
    login = client.post(
        "/api/auth/login",
        json={"email": "author@example.com", "password": "a-secure-password"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "submitter"
    assert login.json()["email_verified_at"]


def test_registration_does_not_allow_role_injection(
    client: TestClient, db_session: Session
) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "intruder@example.com",
            "display_name": "测试",
            "password": "a-secure-password",
            "role": "admin",
        },
    )
    assert response.status_code == 202
    assert db_session.query(User).filter_by(
        email="intruder@example.com"
    ).one().role == ("submitter")


def test_unverified_submitter_can_request_a_new_verification_link(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    from src.api.routers import auth

    client.post(
        "/api/auth/register",
        json={
            "email": "resend@example.com",
            "display_name": "补发测试",
            "password": "a-secure-password",
        },
    )
    monkeypatch.setattr(auth.settings, "registration_resend_cooldown_seconds", 0)

    resent = client.post(
        "/api/auth/email-verification/resend",
        json={"email": "resend@example.com"},
    )

    assert resent.status_code == 202
    tokens = (
        db_session.query(EmailVerificationToken)
        .order_by(EmailVerificationToken.created_at)
        .all()
    )
    assert len(tokens) == 2
    assert tokens[0].used_at is not None
    assert tokens[1].used_at is None
