"""로컬 개발용 시드 데이터 생성 (멱등).

슈퍼유저 + 데모 유저, 유저별 태그, todo/schedule/reflection, 캐릭터,
퀘스트, 피드(post)를 생성한다.
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
from apps.posts.models import Post
from apps.quests.models import Quest
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

# 시드 캐릭터/피드 이미지 URL (유저별로 다른 이미지).
# - 기본값: dev 서버가 서빙하는 로컬 static 파일.
# - S3/CloudFront 등에 직접 올린 이미지를 쓰려면 아래 env 에 전체 URL 을 넣으면 그대로
#   사용된다(재시드 시 기존 캐릭터/피드 이미지도 이 값으로 갱신됨).
#   파일명/키를 역할별로 둬서 어느 유저(seed) 이미지인지 식별 가능하게 한다.
#   예) SEED_DEMO_IMAGE_URL=https://<bucket>.s3.ap-northeast-2.amazonaws.com/mongle-village/seed/demo-character.png
SEED_IMAGE_BASE_URL = os.environ.get("SEED_IMAGE_BASE_URL") or "http://localhost:8000"


def _seed_image_url(env_key: str, filename: str) -> str:
    # `.env` 에 빈 값으로 선언돼도(예: SEED_DEMO_IMAGE_URL=) 기본값으로 떨어지도록
    # get(...) 대신 `or` 로 빈 문자열까지 함께 걸러낸다.
    return os.environ.get(env_key) or f"{SEED_IMAGE_BASE_URL}/static/seed/{filename}"


SEED_DEMO_IMAGE_URL = _seed_image_url("SEED_DEMO_IMAGE_URL", "demo-character.png")
SEED_ADMIN_IMAGE_URL = _seed_image_url("SEED_ADMIN_IMAGE_URL", "admin-character.png")


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
            seed_targets = (
                (admin, SEED_ADMIN_IMAGE_URL),
                (demo, SEED_DEMO_IMAGE_URL),
            )
            for user, image_url in seed_targets:
                tags = self._seed_tags(user)
                todos = self._seed_todos(user, tags)
                self._seed_schedule(user, tags)
                self._seed_reflection(user)
                character = self._seed_character(user, image_url)
                quests = self._seed_quests(character, todos)
                self._seed_posts(character, quests, image_url)
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
                "is_staff": False,
                "is_superuser": False,
            },
        )
        if created:
            demo.set_password("mongle1234!")
            demo.save(update_fields=["password"])
            self.stdout.write("데모유저 생성: demo@mongle.dev")
        elif demo.is_staff or demo.is_superuser:
            # 데모 계정은 일반 사용자여야 한다. 과거 시드/수동 변경으로 관리자 권한이
            # 남아 있으면 시드를 다시 돌릴 때 강등시켜 항상 일반 권한을 보장한다.
            demo.is_staff = False
            demo.is_superuser = False
            demo.save(update_fields=["is_staff", "is_superuser"])
            self.stdout.write("데모유저 관리자 권한 회수: demo@mongle.dev")
        return demo

    def _seed_tags(self, user: Any) -> dict[str, Tag]:
        tags: dict[str, Tag] = {}
        for content, color in DEFAULT_TAGS:
            tag, _ = Tag.objects.get_or_create(
                user=user, content=content, defaults={"color": color}
            )
            tags[content] = tag
        return tags

    def _seed_todos(self, user: Any, tags: dict[str, Tag]) -> dict[str, Todo]:
        today = timezone.localdate()
        samples = (
            ("아침 스트레칭", tags["건강"], Todo.Status.COMPLETED, today),
            ("기획서 초안 작성", tags["업무"], Todo.Status.IN_PROGRESS, today),
            ("Django 마이그레이션 공부", tags["공부"], Todo.Status.IN_PROGRESS, today),
        )
        todos: dict[str, Todo] = {}
        for content, tag, status, todo_date in samples:
            todo, _ = Todo.objects.get_or_create(
                user=user,
                content=content,
                todo_date=todo_date,
                defaults={"tag": tag, "status": status},
            )
            todos[content] = todo
        return todos

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

    def _seed_character(self, user: Any, image_url: str) -> Character:
        character, created = Character.objects.get_or_create(
            user=user,
            character_name="몽글",
            defaults={
                "gen_img_url": image_url,
                "persona": "따뜻하고 긍정적인 성격의 몽글이. 사용자를 응원한다.",
                "visual": "포근한 숲속 마을에 사는 아기 동물 캐릭터",
                "is_active": True,
            },
        )
        # 이미 만들어진 캐릭터는 get_or_create 가 갱신하지 않으므로, 시드 이미지를
        # 항상 최신으로 맞춰 재실행 시에도 동일한 캐릭터 이미지를 보장한다.
        if not created and character.gen_img_url != image_url:
            character.gen_img_url = image_url
            character.save(update_fields=["gen_img_url"])
        return character

    def _seed_quests(
        self, character: Character, todos: dict[str, Todo]
    ) -> dict[str, Quest]:
        # (todo 내용, 퀘스트 내용, 상태, 캐릭터 반응)
        samples = (
            (
                "아침 스트레칭",
                "몽글이와 함께 아침 스트레칭으로 하루 열기",
                Quest.Status.COMPLETED,
                "기지개 쫙! 덕분에 나도 개운해졌어 🦊",
            ),
            (
                "기획서 초안 작성",
                "기획서 초안 완성하고 한 숨 돌리기",
                Quest.Status.IN_PROGRESS,
                "조금만 더 힘내자, 내가 옆에서 응원할게!",
            ),
            (
                "Django 마이그레이션 공부",
                "마이그레이션 개념 한 가지 정리하기",
                Quest.Status.IN_PROGRESS,
                "오늘도 한 뼘 성장하는 중! 멋져 🌱",
            ),
        )
        quests: dict[str, Quest] = {}
        for todo_key, content, status, reaction in samples:
            todo = todos.get(todo_key)
            if todo is None:
                continue
            quest, _ = Quest.objects.get_or_create(
                character=character,
                todo=todo,
                defaults={
                    "content": content,
                    "status": status,
                    "character_reaction": reaction,
                },
            )
            quests[todo_key] = quest
        return quests

    def _seed_posts(
        self, character: Character, quests: dict[str, Quest], image_url: str
    ) -> None:
        # (연결할 퀘스트 키, 피드 내용, 좋아요 여부)
        samples = (
            (
                "아침 스트레칭",
                "오늘 아침 스트레칭 미션 클리어! 개운하게 하루 시작 🦊✨",
                True,
            ),
            (
                "기획서 초안 작성",
                "기획서랑 씨름 중... 그래도 몽글이가 응원해줘서 힘이 나!",
                False,
            ),
            (
                "Django 마이그레이션 공부",
                "Django 마이그레이션 공부 시작! 오늘도 한 걸음 성장 🌱",
                False,
            ),
        )
        for quest_key, content, is_liked in samples:
            quest = quests.get(quest_key)
            if quest is None:
                continue
            post, created = Post.objects.get_or_create(
                character=character,
                content=content,
                defaults={
                    "quest": quest,
                    "img_url": image_url,
                    "is_liked": is_liked,
                },
            )
            # get_or_create 는 기존 피드를 갱신하지 않으므로, 이미지 URL 이 바뀌면
            # (예: 로컬 static → S3) 재시드 시 기존 피드 이미지도 맞춰 준다.
            if not created and post.img_url != image_url:
                post.img_url = image_url
                post.save(update_fields=["img_url"])
