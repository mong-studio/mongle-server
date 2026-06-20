"""카카오 OAuth 토큰 교환 및 프로필 조회 (httpx)."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
import httpx

KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"  # noqa: S105  # URL, not a secret
KAKAO_PROFILE_URL = "https://kapi.kakao.com/v2/user/me"
_TIMEOUT = 5.0


class KakaoError(Exception):
    """카카오 통신/응답 실패."""


@dataclass(frozen=True)
class KakaoProfile:
    provider_id: str
    email: str | None


def exchange_code_for_token(code: str) -> str:
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_REST_API_KEY,
        "client_secret": settings.KAKAO_CLIENT_SECRET,
        "redirect_uri": settings.KAKAO_REDIRECT_URI,
        "code": code,
    }
    try:
        response = httpx.post(KAKAO_TOKEN_URL, data=data, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise KakaoError("카카오 토큰 교환 요청 실패") from exc
    if response.status_code != 200:
        raise KakaoError(f"카카오 토큰 교환 실패: {response.status_code}")
    token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise KakaoError("카카오 access_token 누락")
    return token


def fetch_kakao_profile(access_token: str) -> KakaoProfile:
    try:
        response = httpx.get(
            KAKAO_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise KakaoError("카카오 프로필 조회 요청 실패") from exc
    if response.status_code != 200:
        raise KakaoError(f"카카오 프로필 조회 실패: {response.status_code}")
    body = response.json()
    provider_id = str(body.get("id", ""))
    if not provider_id:
        raise KakaoError("카카오 사용자 id 누락")
    account = body.get("kakao_account") or {}
    email = account.get("email")
    return KakaoProfile(
        provider_id=provider_id,
        email=email if isinstance(email, str) and email else None,
    )
