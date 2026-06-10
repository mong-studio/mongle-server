from __future__ import annotations

from django.test import Client


# 서버 상태 확인 엔드포인트가 200과 {"status": "ok"}를 반환하는지 확인
def test_health_endpoint_returns_ok() -> None:
    response = Client().get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
