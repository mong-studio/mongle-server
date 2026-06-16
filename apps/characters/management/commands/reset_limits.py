"""개발용 캐릭터 한도 초기화 명령.

특정 유저의 두 가지 한도를 한 번에 푼다.
- 활성 캐릭터를 비활성화(soft-delete)해 캐릭터 생성 한도(MAX_ACTIVE_CHARACTERS)를 푼다.
- 오늘자 생성 로그(ImgGenLog)를 삭제해 하루 생성 한도(MAX_DAILY_GEN)를 푼다.
  (생성 실패도 로그가 쌓여 하루 한도를 소모하므로, 실패 누적분도 함께 정리된다.)

사용:
    python manage.py reset_limits --email demo@mongle.dev
    python manage.py reset_limits --email demo@mongle.dev --keep-seed
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.characters.models import Character, ImgGenLog

User = get_user_model()

# 시드 캐릭터 이름(seed_dev 와 동일). --keep-seed 시 보존 대상.
SEED_CHARACTER_NAME = "몽글"


class Command(BaseCommand):
    help = "특정 유저의 캐릭터/하루 생성 한도를 초기화한다(개발용)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--email", required=True, help="초기화할 유저 이메일")
        parser.add_argument(
            "--keep-seed",
            action="store_true",
            help=f"시드 캐릭터('{SEED_CHARACTER_NAME}')는 남겨둔다",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        email: str = options["email"]
        keep_seed: bool = options["keep_seed"]

        if not User.objects.filter(email=email).exists():
            raise CommandError(f"유저를 찾을 수 없습니다: {email}")

        deactivated = self._reset_characters(email, keep_seed)
        deleted_logs = self._reset_daily_generation(email)

        active_remaining = Character.objects.filter(
            user__email=email, is_active=True
        ).count()
        self.stdout.write(self.style.SUCCESS(f"{email} 한도 초기화 완료"))
        self.stdout.write(
            f"  캐릭터 비활성화: {deactivated}개 → 현재 활성 {active_remaining}개"
        )
        self.stdout.write(f"  오늘 생성 로그 삭제: {deleted_logs}개")

    def _reset_characters(self, email: str, keep_seed: bool) -> int:
        qs = Character.objects.filter(user__email=email, is_active=True)
        if keep_seed:
            qs = qs.exclude(character_name=SEED_CHARACTER_NAME)
        return qs.update(is_active=False)

    def _reset_daily_generation(self, email: str) -> int:
        deleted, _ = ImgGenLog.objects.filter(
            user__email=email, created_at__date=timezone.localdate()
        ).delete()
        return deleted
