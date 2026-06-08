"""refresh_token_service 단위 테스트."""

from __future__ import annotations

from datetime import timedelta
import hashlib

from django.http import HttpResponse
from django.utils import timezone
import pytest

from apps.users.models import RefreshToken, User
from apps.users.refresh_token_service import (
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_LIFETIME,
    clear_refresh_cookie,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
    set_refresh_cookie,
    validate_refresh_token,
)


@pytest.mark.django_db
def test_issue_stores_hash_not_raw_token(user: User) -> None:
    """DB에 토큰 해시 후 저장"""
    raw, expires_at = issue_refresh_token(user, device_info="pytest-agent")

    row = RefreshToken.objects.get(user=user)
    assert row.token_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert row.token_hash != raw
    assert row.device_info == "pytest-agent"
    # 2주 만료 (오차 1시간 허용)
    delta = row.expires_at - timezone.now()
    assert timedelta(days=13, hours=23) < delta <= timedelta(weeks=2)
    assert row.expires_at == expires_at
    # 기본은 영구(persistent) 토큰
    assert row.persistent is True


@pytest.mark.django_db
def test_issue_non_persistent_stores_flag(user: User) -> None:
    """persistent=False로 발급하면 세션 토큰으로 DB에 표시된다."""
    issue_refresh_token(user, persistent=False)
    row = RefreshToken.objects.get(user=user)
    assert row.persistent is False


@pytest.mark.django_db
def test_rotate_inherits_persistent_flag(user: User) -> None:
    """토큰을 회전해도 원래의 세션/영구 성격을 그대로 물려받는다."""
    raw, _ = issue_refresh_token(user, persistent=False)
    row = validate_refresh_token(raw)
    assert row is not None

    rotated = rotate_refresh_token(row)
    assert rotated is not None
    new_raw, _ = rotated

    new_row = validate_refresh_token(new_raw)
    assert new_row is not None
    assert new_row.persistent is False  # 세션 토큰은 회전해도 세션 유지


def test_set_refresh_cookie_session_has_no_max_age() -> None:
    """persistent=False 쿠키는 만료시각 없는 세션 쿠키로 설정된다."""
    response = HttpResponse()
    set_refresh_cookie(response, "raw-token-value", persistent=False)

    cookie = response.cookies[REFRESH_COOKIE_NAME]
    assert cookie.value == "raw-token-value"
    assert cookie["httponly"]
    assert cookie["max-age"] == ""  # 세션 쿠키 → 만료시각 없음
    assert cookie["expires"] == ""


@pytest.mark.django_db
def test_validate_returns_row_for_valid_token(user: User) -> None:
    """유효한 토큰으로 validate를 호출하면 해당 사용자의 RefreshToken 행을 반환한다."""
    raw, _ = issue_refresh_token(user)
    row = validate_refresh_token(raw)
    assert row is not None
    assert row.user == user


@pytest.mark.django_db
def test_validate_returns_none_for_unknown_token(db: None) -> None:
    """존재하지 않는 토큰으로 validate를 호출하면 None을 반환한다."""
    assert validate_refresh_token("forged-token") is None


@pytest.mark.django_db
def test_rotate_invalidates_old_and_issues_new(user: User) -> None:
    """토큰 rotate 시 이전 토큰은 무효화 후 새 토큰이 발급. device_info가 갱신"""
    raw_old, _ = issue_refresh_token(user, device_info="device-a")
    row = validate_refresh_token(raw_old)
    assert row is not None

    rotated = rotate_refresh_token(row)
    assert rotated is not None
    raw_new, _ = rotated

    assert validate_refresh_token(raw_old) is None
    new_row = validate_refresh_token(raw_new)
    assert new_row is not None
    assert new_row.user == user
    assert new_row.device_info == "device-a"  # device_info 승계
    assert RefreshToken.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_rotate_already_deleted_row_returns_none(user: User) -> None:
    """동시 rotation(또는 replay) 시 두 번째 호출은 발급 없이 None을 반환한다."""
    raw, _ = issue_refresh_token(user, device_info="device-a")
    row = validate_refresh_token(raw)
    assert row is not None
    same_row = validate_refresh_token(raw)
    assert same_row is not None

    first = rotate_refresh_token(row)
    second = rotate_refresh_token(same_row)

    assert first is not None
    assert second is None
    assert RefreshToken.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_revoke_deletes_only_matching_row(user: User) -> None:
    """특정 토큰을 revoke하면 해당 행만 삭제되고 다른 기기의 토큰은 유지된다."""
    raw_a, _ = issue_refresh_token(user, device_info="device-a")
    raw_b, _ = issue_refresh_token(user, device_info="device-b")

    revoke_refresh_token(raw_a)

    assert validate_refresh_token(raw_a) is None
    assert validate_refresh_token(raw_b) is not None


@pytest.mark.django_db
def test_revoke_unknown_token_is_noop(db: None) -> None:
    """존재하지 않는 토큰을 revoke해도 예외 없이 정상 통과한다."""
    revoke_refresh_token("forged-token")  # 예외 없이 통과


def test_set_refresh_cookie_attributes() -> None:
    """set_refresh_cookie가 httponly·path·samesite·max-age 속성을 올바르게 설정한다."""
    response = HttpResponse()
    set_refresh_cookie(response, "raw-token-value")

    cookie = response.cookies[REFRESH_COOKIE_NAME]
    assert cookie.value == "raw-token-value"
    assert cookie["httponly"]
    assert cookie["path"] == "/api/v1/auth"
    assert cookie["samesite"] == "Lax"
    assert cookie["max-age"] == int(REFRESH_TOKEN_LIFETIME.total_seconds())


def test_clear_refresh_cookie_expires_cookie() -> None:
    """clear_refresh_cookie가 빈 값과 max-age=0으로 쿠키를 만료 처리한다."""
    response = HttpResponse()
    clear_refresh_cookie(response)

    cookie = response.cookies[REFRESH_COOKIE_NAME]
    assert cookie.value == ""
    assert cookie["path"] == "/api/v1/auth"
    assert cookie["max-age"] == 0


@pytest.mark.django_db
def test_cleanup_expired_refresh_tokens(user: User) -> None:
    """만료된 리프레시 토큰만 삭제되고 유효한 토큰은 그대로 남아 있음을 검증한다."""
    from apps.users.tasks import cleanup_expired_refresh_tokens

    raw_valid, _ = issue_refresh_token(user, device_info="valid")
    issue_refresh_token(user, device_info="expired")
    RefreshToken.objects.filter(device_info="expired").update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )

    cleanup_expired_refresh_tokens()

    assert RefreshToken.objects.count() == 1
    assert validate_refresh_token(raw_valid) is not None
