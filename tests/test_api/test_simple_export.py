# tests/test_api/test_simple_export.py
import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_export_simple_report_requires_auth(client):
    """测试简洁版导出需要认证"""
    response = client.get("/api/papers/1/export/simple")
    assert response.status_code == 401
