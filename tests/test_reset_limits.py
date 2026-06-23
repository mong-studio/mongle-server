"""reset_limits 관리 명령 테스트."""

from __future__ import annotations

import datetime
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
import pytest

from apps.characters.models import Character, ImgGenLog

User = get_user_model()


def _make_user(email: str) -> object:
    return User.objects.create(
        email=email, user_name="몽글이", birth=datetime.date(2000, 1, 1)
    )


def _make_character(user: object, name: str) -> Character:
    return Character.objects.create(
        user=user,
        character_name=name,
        gen_img_url="http://example.com/x.png",
        persona="테스트 캐릭터",
    )


def _run(**kwargs: object) -> str:
    out = StringIO()
    call_command("reset_limits", stdout=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
def test_reset_deactivates_characters_and_clears_daily_logs() -> None:
    user = _make_user("demo@mongle.dev")
    for name in ("몽글", "라니", "마루"):
        _make_character(user, name)
    ImgGenLog.objects.create(user=user, gen_cnt=1)
    ImgGenLog.objects.create(user=user, gen_cnt=2)

    _run(email="demo@mongle.dev")

    # keep-seed 없이는 시드 포함 전부 비활성화
    assert Character.objects.filter(user=user, is_active=True).count() == 0
    assert ImgGenLog.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_keep_seed_preserves_seed_character() -> None:
    user = _make_user("demo@mongle.dev")
    for name in ("몽글", "라니", "마루"):
        _make_character(user, name)

    _run(email="demo@mongle.dev", keep_seed=True)

    active = list(
        Character.objects.filter(user=user, is_active=True).values_list(
            "character_name", flat=True
        )
    )
    assert active == ["몽글"]


@pytest.mark.django_db
def test_daily_only_clears_logs_but_keeps_characters() -> None:
    user = _make_user("demo@mongle.dev")
    _make_character(user, "라니")
    ImgGenLog.objects.create(user=user, gen_cnt=1)

    _run(email="demo@mongle.dev", daily_only=True)

    # 오늘자 생성 로그만 지우고 캐릭터는 활성 그대로 둔다.
    assert ImgGenLog.objects.filter(user=user).count() == 0
    assert Character.objects.filter(user=user, is_active=True).count() == 1


@pytest.mark.django_db
def test_reset_only_targets_requested_user() -> None:
    target = _make_user("demo@mongle.dev")
    other = _make_user("other@mongle.dev")
    _make_character(target, "라니")
    _make_character(other, "콩이")
    ImgGenLog.objects.create(user=other, gen_cnt=1)

    _run(email="demo@mongle.dev")

    # 다른 유저의 캐릭터/로그는 건드리지 않는다.
    assert Character.objects.filter(user=other, is_active=True).count() == 1
    assert ImgGenLog.objects.filter(user=other).count() == 1


@pytest.mark.django_db
def test_unknown_email_raises_command_error() -> None:
    with pytest.raises(CommandError):
        _run(email="nobody@mongle.dev")
