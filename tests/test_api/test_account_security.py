from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.field_encryption import decrypt_field
from src.models.api_key import ApiKey
from src.models.editorial import EmailDelivery
from src.models.user import Invitation, PasswordResetToken
from tests.test_api.conftest import create_user


def _login(client: TestClient, email: str, password: str = "secret123") -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200


def test_password_change_invalidates_old_session_and_optionally_keys(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session, email="editor@example.com", role="editor")
    _login(client, "editor@example.com")
    old_cookie = client.cookies.get("socialeval_session")
    created = client.post(
        "/api/auth/api-keys",
        json={"name": "自动化测试", "expires_in_days": 30},
    )
    assert created.status_code == 201

    changed = client.post(
        "/api/auth/password/change",
        json={
            "current_password": "secret123",
            "new_password": "a-new-secure-password",
            "revoke_api_keys": True,
        },
    )
    assert changed.status_code == 200

    with TestClient(client.app) as old_client:
        old_client.cookies.set("socialeval_session", old_cookie)
        assert old_client.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "editor@example.com", "password": "secret123"},
        ).status_code
        == 401
    )
    _login(client, "editor@example.com", "a-new-secure-password")
    keys = client.get("/api/auth/api-keys").json()
    assert keys[0]["is_active"] is False


def test_password_reset_token_is_encrypted_in_outbox_and_single_use(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session, email="expert@example.com", role="expert")
    response = client.post(
        "/api/auth/password-reset/request",
        json={"email": "expert@example.com"},
    )
    assert response.status_code == 202
    token_row = db_session.query(PasswordResetToken).one()
    delivery = (
        db_session.query(EmailDelivery)
        .filter(EmailDelivery.event_type == "password_reset_requested")
        .one()
    )
    assert "token" not in (delivery.template_data or {})
    raw_token = decrypt_field(delivery.template_data["token_encrypted"])
    assert raw_token not in token_row.token_hash

    confirm = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "reset-secure-password"},
    )
    assert confirm.status_code == 204
    repeated = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "another-secure-password"},
    )
    assert repeated.status_code == 400
    _login(client, "expert@example.com", "reset-secure-password")


def test_invitation_stores_only_hash(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session, email="admin@example.com", role="admin")
    _login(client, "admin@example.com")
    response = client.post(
        "/api/users/invitations",
        json={"email": "new@example.com", "role": "editor"},
    )
    assert response.status_code == 201
    raw_token = response.json()["token"]
    invitation = db_session.query(Invitation).one()
    assert invitation.token is None
    assert invitation.token_hash
    assert raw_token not in invitation.token_hash


def test_production_admin_mfa_setup_and_login(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    admin = create_user(db_session, email="admin@example.com", role="admin")
    monkeypatch.setattr(settings, "admin_mfa_required", True)

    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )
    assert login.json()["status"] == "mfa_setup_required"
    setup = client.post("/api/auth/mfa/setup")
    assert setup.status_code == 200
    db_session.refresh(admin)
    secret = decrypt_field(admin.mfa_secret_encrypted)
    code = pyotp.TOTP(secret).now()
    confirmed = client.post("/api/auth/mfa/confirm", json={"code": code})
    assert confirmed.status_code == 200
    original_recovery_codes = confirmed.json()["recovery_codes"]
    assert len(original_recovery_codes) == 10
    assert client.get("/api/auth/me").status_code == 200

    regenerated = client.post(
        "/api/auth/mfa/recovery-codes/regenerate",
        json={"password": "secret123", "code": pyotp.TOTP(secret).now()},
    )
    assert regenerated.status_code == 200
    assert len(regenerated.json()["recovery_codes"]) == 10
    assert regenerated.json()["recovery_codes"] != original_recovery_codes

    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )
    assert login.json()["status"] == "mfa_required"
    verified = client.post(
        "/api/auth/mfa/verify",
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert verified.status_code == 200


def test_admin_cannot_deactivate_last_admin(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = create_user(db_session, email="admin@example.com", role="admin")
    _login(client, "admin@example.com")
    response = client.patch(
        f"/api/users/{admin.id}",
        json={"is_active": False},
    )
    assert response.status_code == 409


def test_admin_password_reset_immediately_blocks_old_credentials(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session, email="admin@example.com", role="admin")
    editor = create_user(db_session, email="editor@example.com", role="editor")
    with TestClient(client.app) as editor_client:
        _login(editor_client, editor.email)
        old_cookie = editor_client.cookies.get("socialeval_session")

        _login(client, "admin@example.com")
        requested = client.post(f"/api/users/{editor.id}/password-reset")
        assert requested.status_code == 202

        editor_client.cookies.set("socialeval_session", old_cookie)
        assert editor_client.get("/api/auth/me").status_code == 401
        old_login = editor_client.post(
            "/api/auth/login",
            json={"email": editor.email, "password": "secret123"},
        )
        assert old_login.status_code == 403
        assert "重置密码" in old_login.json()["detail"]

        delivery = (
            db_session.query(EmailDelivery)
            .filter(EmailDelivery.event_type == "password_reset_requested")
            .order_by(EmailDelivery.created_at.desc())
            .first()
        )
        raw_token = decrypt_field(delivery.template_data["token_encrypted"])
        confirmed = editor_client.post(
            "/api/auth/password-reset/confirm",
            json={
                "token": raw_token,
                "new_password": "forced-reset-secure-password",
            },
        )
        assert confirmed.status_code == 204
        _login(editor_client, editor.email, "forced-reset-secure-password")


def test_role_change_invalidates_session_and_api_keys(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session, email="admin@example.com", role="admin")
    editor = create_user(db_session, email="editor@example.com", role="editor")
    with TestClient(client.app) as editor_client:
        _login(editor_client, editor.email)
        old_cookie = editor_client.cookies.get("socialeval_session")
        created = editor_client.post(
            "/api/auth/api-keys",
            json={"name": "角色变更测试", "expires_in_days": 30},
        )
        assert created.status_code == 201
        api_key_id = created.json()["id"]

        _login(client, "admin@example.com")
        changed = client.patch(
            f"/api/users/{editor.id}",
            json={"role": "expert"},
        )
        assert changed.status_code == 200

        editor_client.cookies.set("socialeval_session", old_cookie)
        assert editor_client.get("/api/auth/me").status_code == 401
        db_session.expire_all()
        assert db_session.get(ApiKey, api_key_id).is_active is False
