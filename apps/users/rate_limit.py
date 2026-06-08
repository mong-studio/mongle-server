"""캐시 기반 고정 윈도우 레이트 리미터 (brute-force 방어용)."""

from __future__ import annotations

from django.core.cache import cache
from django.http import HttpRequest


def client_ip(request: HttpRequest) -> str:
    """위조 불가능한 REMOTE_ADDR 기반 클라이언트 IP.

    프록시/로드밸런서 뒤에 배포할 경우, 신뢰 가능한 프록시가 설정한
    헤더(X-Forwarded-For 등)를 별도로 신뢰 처리해야 한다. 여기서는
    스푸핑을 막기 위해 REMOTE_ADDR만 사용한다.
    """
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def hit_rate_limit(key: str, *, limit: int, window_seconds: int) -> bool:
    """요청 1건을 기록하고, 윈도우 내 누적이 limit을 초과하면 True를 반환한다.

    고정 윈도우 방식: cache.add로 윈도우 시작 시 TTL을 설정하고,
    cache.incr로 원자적으로 카운트한다. 공유 캐시(Redis)를 사용하면
    여러 워커 프로세스 간에도 카운트가 일관된다.
    """
    cache_key = f"ratelimit:{key}"
    if cache.add(cache_key, 1, timeout=window_seconds):
        return limit < 1
    try:
        current = cache.incr(cache_key)
    except ValueError:
        # 윈도우가 incr 직전에 만료됨 — 새 윈도우를 시작한다.
        cache.add(cache_key, 1, timeout=window_seconds)
        return limit < 1
    return current > limit
