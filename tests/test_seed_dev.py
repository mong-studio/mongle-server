"""seed_dev 관리 명령 테스트."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
import pytest

from apps.characters.models import Character
from apps.posts.models import Post
from apps.quests.models import Quest
from apps.tags.models import Tag
from apps.todos.models import Reflection, Schedule, Todo
from apps.users.models import User


def _run(**kwargs: object) -> str:
    out = StringIO()
    call_command("seed_dev", stdout=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
def test_seed_dev_creates_superuser_and_demo_user() -> None:
    _run()

    admin = User.objects.get(email="admin@mongle.dev")
    assert admin.is_superuser and admin.is_staff
    assert admin.check_password("mongle1234!")

    demo = User.objects.get(email="demo@mongle.dev")
    assert not demo.is_superuser
    assert not demo.is_staff
    assert demo.check_password("mongle1234!")


@pytest.mark.django_db
def test_seed_dev_demotes_demo_user_with_admin_rights() -> None:
    """관리자 권한이 남은 데모 계정은 시드 재실행 시 일반 권한으로 강등된다."""
    _run()
    User.objects.filter(email="demo@mongle.dev").update(
        is_staff=True, is_superuser=True
    )

    output = _run()

    demo = User.objects.get(email="demo@mongle.dev")
    assert not demo.is_staff
    assert not demo.is_superuser
    assert "관리자 권한 회수" in output


@pytest.mark.django_db
def test_seed_dev_creates_per_user_sample_data() -> None:
    _run()

    # 유저 2명 x 태그 5개
    assert Tag.objects.count() == 10
    assert User.objects.count() == 2
    for user in User.objects.all():
        assert user.tags.count() == 5
        assert Todo.objects.filter(user=user).count() == 3
        assert Schedule.objects.filter(user=user).count() == 1
        assert Reflection.objects.filter(user=user).count() == 1
        assert Character.objects.filter(user=user).count() == 1
        character = Character.objects.get(user=user)
        assert character.gen_img_url.endswith("/static/seed/mongle-fox.png")
        assert Quest.objects.filter(character=character).count() == 3
        assert Post.objects.filter(character=character).count() == 3


@pytest.mark.django_db
def test_seed_dev_is_idempotent() -> None:
    _run()
    second = _run()

    assert User.objects.count() == 2
    assert Tag.objects.count() == 10
    assert Todo.objects.count() == 6
    assert Quest.objects.count() == 6
    assert Post.objects.count() == 6
    assert "존재(스킵)" in second


@pytest.mark.django_db
def test_seed_dev_accepts_custom_credentials() -> None:
    _run(email="owner@mongle.dev", password="custom-pass-1!")

    admin = User.objects.get(email="owner@mongle.dev")
    assert admin.is_superuser
    assert admin.check_password("custom-pass-1!")
