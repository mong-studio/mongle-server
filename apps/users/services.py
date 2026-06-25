"""회원 관련 도메인 서비스."""

from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.characters.models import Character, SourceImage
from apps.users.models import SocialAccount, User
from infrastructure.storage.s3 import delete_object

# birth 는 not-null 이라 익명화 시 실제 생일 대신 쓰는 센티넬 값.
_WITHDRAWN_BIRTH = date(1900, 1, 1)


def _collect_original_image_keys(user: User) -> list[str]:
    """유저의 원본 사진 S3 object key 모음(SourceImage + Character.origin_img_url)."""
    keys = list(
        SourceImage.objects.filter(user=user)
        .exclude(object_key="")
        .values_list("object_key", flat=True)
    )
    keys += list(
        Character.objects.filter(user=user)
        .exclude(origin_img_url="")
        .values_list("origin_img_url", flat=True)
    )
    return keys


def withdraw_user(user: User) -> None:
    """회원 탈퇴 처리.

    개인정보(원본이미지·닉네임·이메일·비밀번호·생년월일·직업)를 삭제/익명화하고
    계정을 비활성화한다. 이용 로그(퀘스트·피드·토큰·생성 횟수 등)는 유지하기 위해
    User 행 자체는 지우지 않는다. 원본 사진은 S3 에서 best-effort 로 삭제한다.
    """
    image_keys = _collect_original_image_keys(user)

    with transaction.atomic():
        # 원본 업로드 기록 제거(생성 잡의 FK 는 SET_NULL 이라 잡 로그는 유지)
        SourceImage.objects.filter(user=user).delete()
        # 캐릭터 행은 로그(퀘스트·피드)가 참조하므로 유지하되 원본 사진 키만 비운다
        Character.objects.filter(user=user).update(origin_img_url="")
        # 외부 신원 링크 제거
        SocialAccount.objects.filter(user=user).delete()

        # 개인정보 익명화 + 비활성화 (User 행은 로그 보존 위해 삭제하지 않음)
        user.email = f"withdrawn_{user.user_id}@deleted.invalid"
        user.user_name = "(탈퇴)"
        user.job = ""
        user.birth = _WITHDRAWN_BIRTH
        user.set_unusable_password()
        user.is_active = False
        user.save(
            update_fields=[
                "email",
                "user_name",
                "job",
                "birth",
                "password",
                "is_active",
                "updated_at",
            ]
        )

    # S3 삭제는 트랜잭션 밖에서 best-effort (실패해도 DB 익명화는 유지)
    for key in image_keys:
        delete_object(key)
