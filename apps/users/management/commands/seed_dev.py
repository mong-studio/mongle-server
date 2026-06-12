"""로컬 개발용 시드 데이터 생성 (멱등).

슈퍼유저 + 데모 유저, 유저별 태그, todo/schedule/reflection, 캐릭터를 생성한다.
모두 get_or_create 기반이라 반복 실행해도 중복이 쌓이지 않는다.

사용:
    python manage.py seed_dev
    python manage.py seed_dev --email admin@mongle.dev --password 'secret'
"""

from __future__ import annotations

import datetime
import os
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.characters.models import Character
from apps.tags.models import Tag
from apps.todos.models import Reflection, Schedule, Todo

User = get_user_model()

# 유저별 기본 태그 (content, color)
DEFAULT_TAGS: tuple[tuple[str, str], ...] = (
    ("일반", "#8e6038"),
    ("업무", "#4b7bec"),
    ("건강", "#26de81"),
    ("공부", "#f7b731"),
    ("취미", "#fd9644"),
)


class Command(BaseCommand):
    help = "로컬 개발용 시드 데이터(슈퍼유저 + 샘플 데이터)를 생성한다."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--email", default="admin@mongle.dev")
        parser.add_argument(
            "--password",
            default=os.environ.get("SEED_SUPERUSER_PASSWORD", "mongle1234!"),
            help="슈퍼유저 비밀번호(기본: env SEED_SUPERUSER_PASSWORD 또는 dev 기본값)",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        try:
            admin = self._seed_superuser(options["email"], options["password"])
            demo = self._seed_demo_user()
            for user in (admin, demo):
                tags = self._seed_tags(user)
                self._seed_todos(user, tags)
                self._seed_schedule(user, tags)
                self._seed_reflection(user)
                self._seed_character(user)
        except Exception as error:
            self.stderr.write(self.style.ERROR(f"시드 실패: {error}"))
            raise

        self.stdout.write(self.style.SUCCESS("시드 데이터 생성 완료"))
        self.stdout.write(f"  슈퍼유저: {options['email']} / {options['password']}")
        self.stdout.write("  데모유저: demo@mongle.dev / mongle1234!")

    def _seed_superuser(self, email: str, password: str) -> Any:
        admin, created = User.objects.get_or_create(
            email=email,
            defaults={
                "user_name": "관리자",
                "birth": datetime.date(1995, 1, 1),
                "is_staff": True,
                "is_superuser": True,
                "is_aiconsent": True,
            },
        )
        if created:
            admin.set_password(password)
            admin.save(update_fields=["password"])
            self.stdout.write(f"슈퍼유저 생성: {email}")
        else:
            self.stdout.write(f"슈퍼유저 존재(스킵): {email}")
        return admin

    def _seed_demo_user(self) -> Any:
        demo, created = User.objects.get_or_create(
            email="demo@mongle.dev",
            defaults={
                "user_name": "몽글이",
                "job": "디자이너",
                "birth": datetime.date(2000, 5, 20),
                "is_aiconsent": True,
            },
        )
        if created:
            demo.set_password("mongle1234!")
            demo.save(update_fields=["password"])
            self.stdout.write("데모유저 생성: demo@mongle.dev")
        return demo

    def _seed_tags(self, user: Any) -> dict[str, Tag]:
        tags: dict[str, Tag] = {}
        for content, color in DEFAULT_TAGS:
            tag, _ = Tag.objects.get_or_create(
                user=user, content=content, defaults={"color": color}
            )
            tags[content] = tag
        return tags

    def _seed_todos(self, user: Any, tags: dict[str, Tag]) -> None:
        today = timezone.localdate()
        samples = (
            ("아침 스트레칭", tags["건강"], Todo.Status.COMPLETED, today),
            ("기획서 초안 작성", tags["업무"], Todo.Status.IN_PROGRESS, today),
            ("Django 마이그레이션 공부", tags["공부"], Todo.Status.IN_PROGRESS, today),
        )
        for content, tag, status, todo_date in samples:
            Todo.objects.get_or_create(
                user=user,
                content=content,
                todo_date=todo_date,
                defaults={"tag": tag, "status": status},
            )

    def _seed_schedule(self, user: Any, tags: dict[str, Tag]) -> None:
        today = timezone.localdate()
        Schedule.objects.get_or_create(
            user=user,
            title="팀 회의",
            start_date=today,
            defaults={
                "tag": tags["업무"],
                "description": "주간 스프린트 회의",
                "end_date": today,
            },
        )

    def _seed_reflection(self, user: Any) -> None:
        Reflection.objects.get_or_create(
            user=user,
            reflection_date=timezone.localdate(),
            defaults={
                "good_points": "할 일을 계획대로 마쳤다.",
                "improvement_points": "집중 시간을 더 확보하기.",
            },
        )

    def _seed_character(self, user: Any) -> None:
        Character.objects.get_or_create(
            user=user,
            character_name="몽글",
            defaults={
                "gen_img_url": "https://example.com/characters/mongle.png",
                "persona": "따뜻하고 긍정적인 성격의 몽글이. 사용자를 응원한다.",
                "is_active": True,
            },
        )
