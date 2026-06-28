"""Todos 앱 테스트 - TODO 목록, 상세"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from apps.quests.models import Quest
from apps.tags.models import Tag
from apps.todos.models import Todo
from apps.users.models import TokenTransaction, User


# 비로그인 상태에서 TODO 목록 조회 시 401 반환 확인
@pytest.mark.django_db
def test_todo_list_unauthenticated() -> None:
    client = APIClient()
    response = client.get("/api/v1/todos/")
    assert response.status_code == 401


# TODO가 없을 때 빈 배열 반환 확인
@pytest.mark.django_db
def test_todo_list_empty(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/todos/")
    assert response.status_code == 200
    assert response.json() == []


# 본인의 TODO만 목록에 포함되는지 확인
@pytest.mark.django_db
def test_todo_list_returns_own_todos(auth_client: APIClient, todo: Todo) -> None:
    response = auth_client.get("/api/v1/todos/")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["content"] == "테스트TODO"


# TODO 목록을 todo_date 쿼리로 필터링하는지 확인
@pytest.mark.django_db
def test_todo_list_filters_by_todo_date(
    auth_client: APIClient, todo: Todo, tag: Tag
) -> None:
    Todo.objects.create(
        user=todo.user,
        tag=tag,
        content="오늘TODO",
        todo_date="2026-06-03",
    )

    response = auth_client.get("/api/v1/todos/", {"todo_date": "2026-06-03"})

    assert response.status_code == 200
    body = response.json()
    assert [item["content"] for item in body] == ["오늘TODO"]


# TODO 목록 응답에 연결된 퀘스트 정보가 함께 포함되는지 확인
@pytest.mark.django_db
def test_todo_list_includes_assigned_quest(
    auth_client: APIClient, todo: Todo, quest: Quest
) -> None:
    response = auth_client.get("/api/v1/todos/")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["quest"]["quest_id"] == str(quest.quest_id)
    assert body[0]["quest"]["content"] == quest.content
    assert body[0]["quest"]["character_id"] == str(quest.character_id)
    assert body[0]["quest"]["character_name"] == quest.character.character_name


# 비로그인 상태에서 TODO 상세 조회 시 401 반환 확인
@pytest.mark.django_db
def test_todo_detail_unauthenticated(todo: Todo) -> None:
    client = APIClient()
    response = client.get(f"/api/v1/todos/{todo.todo_id}/")
    assert response.status_code == 401


# TODO 상세 조회 성공 시 content 필드가 올바른지 확인
@pytest.mark.django_db
def test_todo_detail_authenticated(auth_client: APIClient, todo: Todo) -> None:
    response = auth_client.get(f"/api/v1/todos/{todo.todo_id}/")
    assert response.status_code == 200
    assert response.json()["content"] == "테스트TODO"


# 존재하지 않는 todo_id로 조회 시 404 반환 확인
@pytest.mark.django_db
def test_todo_detail_not_found(auth_client: APIClient) -> None:
    response = auth_client.get("/api/v1/todos/00000000-0000-0000-0000-000000000000/")
    assert response.status_code == 404


# tag_id 없이 생성 시 태그 없이(null) 그대로 생성한다
@pytest.mark.django_db
def test_todo_create_without_tag_is_tagless(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/todos/",
        {"content": "태그없음", "todo_date": "2026-06-02"},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["tag_id"] is None
    assert response.json()["tag_content"] is None


# tag_id를 명시하면 생성 성공
@pytest.mark.django_db
def test_todo_create_with_tag(auth_client: APIClient, tag: Tag) -> None:
    response = auth_client.post(
        "/api/v1/todos/",
        {"content": "할일", "todo_date": "2026-06-02", "tag_id": tag.tag_id},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["tag_content"] == tag.content


# TODO 완료 처리 시 연결된 퀘스트도 완료 상태로 변경되는지 확인
@pytest.mark.django_db
def test_todo_complete_marks_linked_quest_completed(
    auth_client: APIClient, todo: Todo, quest: Quest
) -> None:
    response = auth_client.patch(f"/api/v1/todos/{todo.todo_id}/complete/")

    assert response.status_code == 200
    todo.refresh_from_db()
    quest.refresh_from_db()
    assert todo.status == Todo.Status.COMPLETED
    assert quest.status == Quest.Status.COMPLETED


# 포기(fail) 처리 시 연결된 진행 중 퀘스트도 실패 상태로 변경되는지 확인
@pytest.mark.django_db
def test_todo_fail_marks_linked_quest_failed(
    auth_client: APIClient, todo: Todo, quest: Quest
) -> None:
    assert quest.status == Quest.Status.IN_PROGRESS

    response = auth_client.patch(f"/api/v1/todos/{todo.todo_id}/fail/")

    assert response.status_code == 200
    assert response.json()["status"] == Todo.Status.FAILED
    todo.refresh_from_db()
    quest.refresh_from_db()
    assert todo.status == Todo.Status.FAILED
    assert quest.status == Quest.Status.FAILED


@pytest.mark.django_db
def test_todo_complete_rewards_token_and_returns_server_balance(
    auth_client: APIClient, todo: Todo
) -> None:
    # TODO 완료 보상을 거래 내역에 기록하고 갱신된 서버 잔액을 응답하는지 검증한다.
    starting_balance = todo.user.token_balance

    response = auth_client.patch(f"/api/v1/todos/{todo.todo_id}/complete/")

    assert response.status_code == 200
    assert response.json()["reward"] == 1
    assert response.json()["token_balance"] == starting_balance + 1
    todo.user.refresh_from_db()
    assert todo.user.token_balance == starting_balance + 1
    assert TokenTransaction.objects.filter(
        user=todo.user,
        amount=1,
        type="todo_reward",
        reference_id=str(todo.todo_id),
    ).exists()


@pytest.mark.django_db
def test_todo_complete_respects_daily_reward_limit(
    auth_client: APIClient, todo: Todo
) -> None:
    # 하루 10회 보상을 모두 받은 뒤에는 TODO를 완료해도 잔액을 추가하지 않는다.
    starting_balance = todo.user.token_balance
    TokenTransaction.objects.bulk_create(
        [
            TokenTransaction(
                user=todo.user,
                amount=1,
                type="todo_reward",
                reference_id=f"daily-reward-{index}",
            )
            for index in range(10)
        ]
    )

    response = auth_client.patch(f"/api/v1/todos/{todo.todo_id}/complete/")

    assert response.status_code == 200
    assert response.json()["reward"] == 0
    assert response.json()["token_balance"] == starting_balance
    todo.user.refresh_from_db()
    assert todo.user.token_balance == starting_balance


def _past_todo(user: User, tag: Tag, *, status: str = Todo.Status.IN_PROGRESS) -> Todo:
    """오늘보다 닷새 전 날짜의 미완료 TODO."""
    return Todo.objects.create(
        user=user,
        tag=tag,
        content="지난할일",
        todo_date=timezone.localdate() - timedelta(days=5),
        status=status,
    )


# 지난 미완료 TODO를 연장하면 날짜가 옮겨지고 토큰 4개가 차감된다
@pytest.mark.django_db
def test_todo_extend_moves_date_and_charges_token(
    auth_client: APIClient, user: User, tag: Tag
) -> None:
    todo = _past_todo(user, tag)
    starting_balance = user.token_balance  # 기본 5
    new_date = timezone.localdate() + timedelta(days=3)

    response = auth_client.patch(
        f"/api/v1/todos/{todo.todo_id}/extend/",
        {"todo_date": new_date.isoformat()},
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["todo_date"] == new_date.isoformat()
    assert body["status"] == Todo.Status.IN_PROGRESS
    assert body["token_balance"] == starting_balance - 4
    todo.refresh_from_db()
    user.refresh_from_db()
    assert todo.todo_date == new_date
    assert user.token_balance == starting_balance - 4
    assert TokenTransaction.objects.filter(
        user=user,
        amount=-4,
        type="todo_extension",
        reference_id=str(todo.todo_id),
    ).exists()


# 포기(FAILED)했던 지난 TODO를 연장하면 다시 진행 중으로 되살아난다
@pytest.mark.django_db
def test_todo_extend_revives_failed_todo(
    auth_client: APIClient, user: User, tag: Tag
) -> None:
    todo = _past_todo(user, tag, status=Todo.Status.FAILED)
    new_date = timezone.localdate() + timedelta(days=1)

    response = auth_client.patch(
        f"/api/v1/todos/{todo.todo_id}/extend/",
        {"todo_date": new_date.isoformat()},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == Todo.Status.IN_PROGRESS
    todo.refresh_from_db()
    assert todo.status == Todo.Status.IN_PROGRESS


# 오늘 포함 미래 날짜(=오늘)로도 연장할 수 있다
@pytest.mark.django_db
def test_todo_extend_allows_today(auth_client: APIClient, user: User, tag: Tag) -> None:
    todo = _past_todo(user, tag)
    today = timezone.localdate()

    response = auth_client.patch(
        f"/api/v1/todos/{todo.todo_id}/extend/",
        {"todo_date": today.isoformat()},
        format="json",
    )

    assert response.status_code == 200
    todo.refresh_from_db()
    assert todo.todo_date == today


# 이미 완료한 TODO는 연장할 수 없다(409)
@pytest.mark.django_db
def test_todo_extend_rejects_completed(
    auth_client: APIClient, user: User, tag: Tag
) -> None:
    todo = _past_todo(user, tag, status=Todo.Status.COMPLETED)
    new_date = timezone.localdate() + timedelta(days=1)

    response = auth_client.patch(
        f"/api/v1/todos/{todo.todo_id}/extend/",
        {"todo_date": new_date.isoformat()},
        format="json",
    )

    assert response.status_code == 409
    user.refresh_from_db()
    assert user.token_balance == 5  # 차감되지 않음


# 지나지 않은(오늘/미래) TODO는 연장 대상이 아니다(400)
@pytest.mark.django_db
def test_todo_extend_rejects_non_past_todo(
    auth_client: APIClient, user: User, tag: Tag
) -> None:
    todo = Todo.objects.create(
        user=user,
        tag=tag,
        content="오늘할일",
        todo_date=timezone.localdate(),
    )
    new_date = timezone.localdate() + timedelta(days=2)

    response = auth_client.patch(
        f"/api/v1/todos/{todo.todo_id}/extend/",
        {"todo_date": new_date.isoformat()},
        format="json",
    )

    assert response.status_code == 400


# 과거 날짜로는 연장할 수 없다(400)
@pytest.mark.django_db
def test_todo_extend_rejects_past_new_date(
    auth_client: APIClient, user: User, tag: Tag
) -> None:
    todo = _past_todo(user, tag)
    past_date = timezone.localdate() - timedelta(days=1)

    response = auth_client.patch(
        f"/api/v1/todos/{todo.todo_id}/extend/",
        {"todo_date": past_date.isoformat()},
        format="json",
    )

    assert response.status_code == 400
    todo.refresh_from_db()
    assert todo.todo_date == timezone.localdate() - timedelta(days=5)


# 토큰이 부족하면 연장에 실패하고 아무것도 바뀌지 않는다(400)
@pytest.mark.django_db
def test_todo_extend_insufficient_tokens(
    auth_client: APIClient, user: User, tag: Tag
) -> None:
    user.token_balance = 3
    user.save(update_fields=["token_balance"])
    todo = _past_todo(user, tag)
    original_date = todo.todo_date
    new_date = timezone.localdate() + timedelta(days=1)

    response = auth_client.patch(
        f"/api/v1/todos/{todo.todo_id}/extend/",
        {"todo_date": new_date.isoformat()},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INSUFFICIENT_TOKEN_BALANCE"
    todo.refresh_from_db()
    user.refresh_from_db()
    assert todo.todo_date == original_date
    assert user.token_balance == 3
    assert not TokenTransaction.objects.filter(type="todo_extension").exists()


# 다른 사용자의 TODO는 연장할 수 없다(404)
@pytest.mark.django_db
def test_todo_extend_other_user_forbidden(auth_client: APIClient, tag: Tag) -> None:
    other = User.objects.create_user(
        email="other@test.com",
        password="password123",
        user_name="남",
        birth="2000-01-01",
    )
    other_tag = Tag.objects.create(
        tag_id=2, user=other, content="공부", color="#00ff00"
    )
    todo = _past_todo(other, other_tag)
    new_date = timezone.localdate() + timedelta(days=1)

    response = auth_client.patch(
        f"/api/v1/todos/{todo.todo_id}/extend/",
        {"todo_date": new_date.isoformat()},
        format="json",
    )

    assert response.status_code == 404


# 비로그인 상태에서는 연장할 수 없다(401)
@pytest.mark.django_db
def test_todo_extend_unauthenticated(user: User, tag: Tag) -> None:
    todo = _past_todo(user, tag)
    client = APIClient()
    response = client.patch(
        f"/api/v1/todos/{todo.todo_id}/extend/",
        {"todo_date": timezone.localdate().isoformat()},
        format="json",
    )
    assert response.status_code == 401
