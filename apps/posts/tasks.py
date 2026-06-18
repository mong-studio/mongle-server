from __future__ import annotations

import logging

import httpx

from celery import shared_task

logger = logging.getLogger(__name__)

_AI_TIMEOUT = 120.0


@shared_task(bind=True, max_retries=2)
def generate_feed_post(self, quest_id: str) -> None:
    """퀘스트 완료 시 mongle-ai 피드 생성 파이프라인을 호출하고 Post를 저장한다."""
    from django.conf import settings

    from apps.characters.models import Character
    from apps.posts.models import Post
    from apps.quests.models import Quest

    try:
        quest = Quest.objects.select_related("character").get(quest_id=quest_id)
    except Quest.DoesNotExist:
        return

    character: Character = quest.character

    payload = {
        "quest": {
            "quest_id": str(quest.quest_id),
            "quest_text": quest.content,
        },
        "character": {
            "character_id": str(character.character_id),
            "name": character.character_name,
            "personality": character.persona,
            "speech_style": "",
            "appearance_keywords": [character.visual] if character.visual else [],
            "image_url": character.gen_img_url,
        },
    }

    try:
        response = httpx.post(
            f"{settings.AI_SERVICE_URL}/v1/feed/generate",
            json=payload,
            headers={"X-API-Key": settings.AI_SERVICE_TOKEN},
            timeout=_AI_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.exception("feed generation failed: quest_id=%s", quest_id)
        raise self.retry(exc=exc, countdown=30) from exc

    result = response.json().get("result") or {}
    img_url = result.get("image_url", "")
    caption = result.get("caption", "")

    if not img_url or not caption:
        logger.error("feed generation returned empty result: quest_id=%s", quest_id)
        return

    if Post.objects.filter(quest=quest).exists():
        return

    Post.objects.create(
        character=character,
        quest=quest,
        content=caption,
        img_url=img_url,
    )


@shared_task
def generate_character_reply(comment_id: str) -> None:
    """
    [이벤트] 댓글 작성 10분 후 실행
    댓글이 달린 게시물의 캐릭터가 자동으로 답글을 생성한다.
    댓글 작성 시 views.py에서 countdown=600(10분)으로 예약 호출된다.
    현재는 고정 문자열로 생성하며, 추후 AI 생성으로 교체 예정
    """
    from apps.posts.models import Comment, Reply

    try:
        comment = Comment.objects.select_related("post__character").get(
            comment_id=comment_id
        )
    except Comment.DoesNotExist:
        return

    character = comment.post.character

    if Reply.objects.filter(comment=comment, character=character).exists():
        return

    # TODO: AI 생성으로 교체 예정
    content = f"{character.character_name}이(가) 댓글을 확인했어요!"

    Reply.objects.create(
        comment=comment,
        character=character,
        content=content,
    )
