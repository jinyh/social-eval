from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
