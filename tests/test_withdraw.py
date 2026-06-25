"""회원 탈퇴(POST /auth/withdraw) 동작을 검증합니다."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.utils import timezone
import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.characters.models import Character, ImgGenLog, SourceImage
from apps.users.models import SocialAccount, User

WITHDRAW_URL = "/api/v1/auth/withdraw"


def _source_image(user: User, object_key: str) -> SourceImage:
    return SourceImage.objects.create(
        user=user,
        object_key=object_key,
        content_type="image/png",
        status=SourceImage.Status.UPLOAD_COMPLETED,
        expires_at=timezone.now(),
    )


@pytest.mark.django_db
def test_withdraw_email_user_success(auth_client: APIClient, user: User) -> None:
    src = _source_image(user, "orig-1.png")
    char = Character.objects.create(
        user=user,
        character_name="몽이",
        persona="p",
        origin_img_url="char-orig-1.png",
        gen_img_url="gen-1.png",
    )
    log = ImgGenLog.objects.create(user=user, gen_cnt=1)

    with patch("apps.users.services.delete_object") as mock_delete:
        response = auth_client.post(
            WITHDRAW_URL, {"password": "password123"}, format="json"
        )

    assert response.status_code == 204

    user.refresh_from_db()
    assert user.is_active is False
    assert user.email != "test@test.com"
    assert user.user_name == "(탈퇴)"
    assert user.job == ""
    assert user.birth == date(1900, 1, 1)
    assert user.check_password("password123") is False

    # 원본 이미지: SourceImage 삭제 + Character.origin_img_url 비움(행·생성이미지 유지)
    assert not SourceImage.objects.filter(pk=src.pk).exists()
    char.refresh_from_db()
    assert char.origin_img_url == ""
    assert char.gen_img_url == "gen-1.png"

    # 이용 로그는 보존된다.
    assert ImgGenLog.objects.filter(pk=log.pk).exists()

    # 원본 사진 S3 키들이 삭제 호출된다.
    deleted_keys = {call.args[0] for call in mock_delete.call_args_list}
    assert deleted_keys == {"orig-1.png", "char-orig-1.png"}


@pytest.mark.django_db
def test_withdraw_email_user_wrong_password(auth_client: APIClient, user: User) -> None:
    response = auth_client.post(WITHDRAW_URL, {"password": "wrong"}, format="json")

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.is_active is True
    assert user.email == "test@test.com"


@pytest.mark.django_db
def test_withdraw_email_user_requires_password(
    auth_client: APIClient, user: User
) -> None:
    response = auth_client.post(WITHDRAW_URL, {}, format="json")

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_withdraw_social_user_without_password() -> None:
    kakao_user = User.objects.create_user(
        email="kakao@test.com",
        user_name="카카오",
        birth="1999-01-01",
        login_type=User.LoginType.KAKAO,
    )
    SocialAccount.objects.create(
        user=kakao_user, provider="kakao", provider_id="kakao-1"
    )
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(kakao_user).access_token}"
    )

    with patch("apps.users.services.delete_object"):
        response = client.post(WITHDRAW_URL, {}, format="json")

    assert response.status_code == 204
    kakao_user.refresh_from_db()
    assert kakao_user.is_active is False
    assert not SocialAccount.objects.filter(user=kakao_user).exists()


@pytest.mark.django_db
def test_withdraw_blocks_authentication_afterward(
    auth_client: APIClient, user: User
) -> None:
    with patch("apps.users.services.delete_object"):
        response = auth_client.post(
            WITHDRAW_URL, {"password": "password123"}, format="json"
        )
    assert response.status_code == 204

    # is_active=False 라 같은 토큰으로 더 이상 인증되지 않는다.
    assert auth_client.get("/api/v1/auth/me/").status_code == 401
