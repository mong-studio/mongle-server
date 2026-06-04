from __future__ import annotations

from celery import shared_task


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
    # TODO: AI 생성으로 교체 예정
    content = f"{character.character_name}이(가) 댓글을 확인했어요!"

    Reply.objects.create(
        comment=comment,
        character=character,
        content=content,
    )
