from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from apps.tags.models import Tag
from apps.todos.models import Reflection, Todo
from apps.todos.tasks import fail_incomplete_todos
from apps.users.models import Notification, TokenTransaction, User
from apps.users.tasks import send_reflection_notification


@pytest.mark.django_db
def test_reflection_create_rewards_tokens(auth_client: APIClient, user: User) -> None:
    # 두 회고 항목이 보상 기준 길이를 채우면 회고 저장과 토큰 지급 이력이 함께 생성된다.
    response = auth_client.post(
        "/api/v1/reflections/",
        {
            "reflection_date": timezone.localdate().isoformat(),
            "good_points": "a" * 30,
            "improvement_points": "b" * 30,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["token"] == 4
    user.refresh_from_db()
    assert user.token_balance == 9
    reflection = Reflection.objects.get(user=user)
    assert reflection.good_token_rewarded is True
    assert reflection.improvement_token_rewarded is True
    assert TokenTransaction.objects.filter(
        user=user,
        amount=4,
        type="reflection_reward",
        reference_id=str(reflection.reflection_id),
    ).exists()


@pytest.mark.django_db
def test_reflection_create_rejects_duplicate(
    auth_client: APIClient,
    user: User,
) -> None:
    # 같은 사용자는 동일 날짜 회고를 한 번만 확정할 수 있다.
    reflection_date = timezone.localdate()
    Reflection.objects.create(
        user=user,
        reflection_date=reflection_date,
        good_points="좋았던 점",
        improvement_points="아쉬운 점",
    )

    response = auth_client.post(
        "/api/v1/reflections/",
        {
            "reflection_date": reflection_date.isoformat(),
            "good_points": "다른 내용",
            "improvement_points": "다른 내용",
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == "REFLECTION_ALREADY_CONFIRMED"


@pytest.mark.django_db
def test_reflection_create_validates_content(auth_client: APIClient) -> None:
    # 빈 내용이나 최대 길이를 넘긴 회고 내용은 저장하지 않는다.
    response = auth_client.post(
        "/api/v1/reflections/",
        {
            "reflection_date": timezone.localdate().isoformat(),
            "good_points": "",
            "improvement_points": "b" * 401,
        },
        format="json",
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "INVALID_REFLECTION_CONTENT"


@pytest.mark.django_db
def test_reflection_date_detail_returns_own_reflection(
    auth_client: APIClient,
    user: User,
) -> None:
    # 날짜별 조회는 로그인 사용자의 회고와 보상 플래그를 반환한다.
    reflection = Reflection.objects.create(
        user=user,
        reflection_date=timezone.localdate(),
        good_points="좋았던 점",
        improvement_points="아쉬운 점",
        good_token_rewarded=True,
    )

    response = auth_client.get(
        f"/api/v1/reflections/{reflection.reflection_date.isoformat()}/"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reflection_id"] == str(reflection.reflection_id)
    assert body["good_token_rewarded"] is True


@pytest.mark.django_db
def test_reflection_list_returns_past_reflections_in_date_order(
    auth_client: APIClient,
    user: User,
) -> None:
    # 기준일 이전의 본인 회고만 오래된 날짜순으로 반환하는지 검증한다.
    today = timezone.localdate()
    other_user = User.objects.create_user(
        email="reflection-list-other@test.com",
        password="password123",
        user_name="다른유저",
        birth="2000-01-01",
    )
    for reflection_date in (
        today - timedelta(days=1),
        today - timedelta(days=3),
        today,
    ):
        Reflection.objects.create(
            user=user,
            reflection_date=reflection_date,
            good_points=f"{reflection_date} 잘한 점",
            improvement_points=f"{reflection_date} 아쉬운 점",
        )
    Reflection.objects.create(
        user=other_user,
        reflection_date=today - timedelta(days=2),
        good_points="다른 사용자 잘한 점",
        improvement_points="다른 사용자 아쉬운 점",
    )

    response = auth_client.get(
        "/api/v1/reflections/",
        {"before": today.isoformat()},
    )

    assert response.status_code == 200
    assert [item["reflection_date"] for item in response.json()] == [
        (today - timedelta(days=3)).isoformat(),
        (today - timedelta(days=1)).isoformat(),
    ]


@pytest.mark.django_db
def test_reflection_list_returns_empty_array_without_404(
    auth_client: APIClient,
) -> None:
    # 이전 회고가 없을 때 404 대신 빈 목록을 반환하는지 검증한다.
    response = auth_client.get(
        "/api/v1/reflections/",
        {"before": timezone.localdate().isoformat()},
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_reflection_context_splits_completed_and_incomplete_todos(
    auth_client: APIClient,
    user: User,
    tag: Tag,
) -> None:
    # 회고 작성 화면은 완료 TODO와 아직 완료되지 않은 TODO를 분리해서 보여준다.
    reflection_date = timezone.localdate()
    Todo.objects.create(
        user=user,
        tag=tag,
        content="완료",
        todo_date=reflection_date,
        status=Todo.Status.COMPLETED,
    )
    Todo.objects.create(
        user=user,
        tag=tag,
        content="미완료",
        todo_date=reflection_date,
        status=Todo.Status.FAILED,
    )
    Todo.objects.create(
        user=user,
        tag=tag,
        content="진행 중",
        todo_date=reflection_date,
        status=Todo.Status.IN_PROGRESS,
    )

    response = auth_client.get(
        f"/api/v1/reflections/context/{reflection_date.isoformat()}/"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["completed_todos"][0]["content"] == "완료"
    assert [todo["content"] for todo in body["incomplete_todos"]] == [
        "미완료",
        "진행 중",
    ]
    assert body["already_reflected"] is False


@pytest.mark.django_db
def test_reflection_update_charges_tokens(
    auth_client: APIClient,
    user: User,
) -> None:
    # 회고 수정은 내용을 갱신하고 정해진 토큰 비용과 거래 이력을 남긴다.
    user.token_balance = 20
    user.save(update_fields=["token_balance"])
    reflection = Reflection.objects.create(
        user=user,
        reflection_date=timezone.localdate(),
        good_points="좋았던 점",
        improvement_points="아쉬운 점",
    )

    response = auth_client.patch(
        f"/api/v1/reflections/{reflection.reflection_id}/",
        {
            "good_points": "새롭게 잘한 점",
            "improvement_points": "새롭게 아쉬운 점",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["reward"] == -15
    user.refresh_from_db()
    assert user.token_balance == 5
    assert TokenTransaction.objects.filter(
        user=user,
        amount=-15,
        type="reflection_update",
        reference_id=str(reflection.reflection_id),
    ).exists()


@pytest.mark.django_db
def test_today_reflection_update_rewards_newly_eligible_field_once(
    auth_client: APIClient,
    user: User,
) -> None:
    # 오늘 회고를 수정해 보상 조건을 새로 충족하면 해당 항목 보상을 한 번만 지급한다.
    user.token_balance = 50
    user.save(update_fields=["token_balance"])
    reflection = Reflection.objects.create(
        user=user,
        reflection_date=timezone.localdate(),
        good_points="짧은 잘한 점",
        improvement_points="짧은 아쉬운 점",
    )
    url = f"/api/v1/reflections/{reflection.reflection_id}/"
    payload = {
        "good_points": "a" * 30,
        "improvement_points": "짧은 아쉬운 점",
    }

    first_response = auth_client.patch(url, payload, format="json")
    second_response = auth_client.patch(url, payload, format="json")

    assert first_response.status_code == 200
    assert first_response.json()["new_reward"] == 2
    assert first_response.json()["token_delta"] == -13
    assert second_response.status_code == 200
    assert second_response.json()["new_reward"] == 0
    assert second_response.json()["token_delta"] == -15
    reflection.refresh_from_db()
    user.refresh_from_db()
    assert reflection.good_token_rewarded is True
    assert reflection.improvement_token_rewarded is False
    assert user.token_balance == 22
    assert (
        TokenTransaction.objects.filter(
            user=user,
            amount=2,
            type="reflection_reward",
            reference_id=str(reflection.reflection_id),
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_past_reflection_update_does_not_reward_newly_eligible_fields(
    auth_client: APIClient,
    user: User,
) -> None:
    # 과거 회고 수정은 새로 글자 수 조건을 충족해도 추가 보상을 지급하지 않는다.
    user.token_balance = 20
    user.save(update_fields=["token_balance"])
    reflection = Reflection.objects.create(
        user=user,
        reflection_date=timezone.localdate() - timedelta(days=1),
        good_points="짧은 잘한 점",
        improvement_points="짧은 아쉬운 점",
    )

    response = auth_client.patch(
        f"/api/v1/reflections/{reflection.reflection_id}/",
        {
            "good_points": "a" * 30,
            "improvement_points": "b" * 30,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["new_reward"] == 0
    assert response.json()["token_delta"] == -15
    reflection.refresh_from_db()
    user.refresh_from_db()
    assert reflection.good_token_rewarded is False
    assert reflection.improvement_token_rewarded is False
    assert user.token_balance == 5


@pytest.mark.django_db
def test_reflection_update_rejects_insufficient_tokens(
    auth_client: APIClient,
    user: User,
) -> None:
    # 토큰 잔액이 수정 비용보다 적으면 회고를 변경하지 않고 거절한다.
    reflection = Reflection.objects.create(
        user=user,
        reflection_date=timezone.localdate(),
        good_points="좋았던 점",
        improvement_points="아쉬운 점",
    )

    response = auth_client.patch(
        f"/api/v1/reflections/{reflection.reflection_id}/",
        {
            "good_points": "새롭게 잘한 점",
            "improvement_points": "새롭게 아쉬운 점",
        },
        format="json",
    )

    assert response.status_code == 402
    assert response.json()["error"]["message"] == "INSUFFICIENT_TOKEN_BALANCE"


@pytest.mark.django_db
def test_todo_reward_reaching_fifteen_allows_reflection_update(
    auth_client: APIClient,
    user: User,
    tag: Tag,
) -> None:
    # TODO 보상으로 잔액이 수정 비용에 도달하면 이어서 회고를 수정할 수 있어야 한다.
    user.token_balance = 14
    user.save(update_fields=["token_balance"])
    today = timezone.localdate()
    todo = Todo.objects.create(
        user=user,
        tag=tag,
        content="사과 보상 TODO",
        todo_date=today,
    )
    reflection = Reflection.objects.create(
        user=user,
        reflection_date=today,
        good_points="기존 잘한 점",
        improvement_points="기존 아쉬운 점",
    )

    complete_response = auth_client.patch(f"/api/v1/todos/{todo.todo_id}/complete/")
    update_response = auth_client.patch(
        f"/api/v1/reflections/{reflection.reflection_id}/",
        {
            "good_points": "수정한 잘한 점",
            "improvement_points": "수정한 아쉬운 점",
        },
        format="json",
    )

    assert complete_response.status_code == 200
    assert complete_response.json()["token_balance"] == 15
    assert update_response.status_code == 200
    user.refresh_from_db()
    assert user.token_balance == 0


@pytest.mark.django_db
def test_todo_complete_creates_reflection_notification_once(
    auth_client: APIClient,
    user: User,
    tag: Tag,
) -> None:
    # 마지막 남은 TODO를 완료했을 때 요청 문구의 당일 회고 알림을 한 번만 생성한다.
    todo_date = timezone.localdate()
    first = Todo.objects.create(
        user=user, tag=tag, content="첫 번째", todo_date=todo_date
    )
    second = Todo.objects.create(
        user=user, tag=tag, content="두 번째", todo_date=todo_date
    )

    first_response = auth_client.patch(f"/api/v1/todos/{first.todo_id}/complete/")
    assert first_response.status_code == 200
    assert Notification.objects.count() == 0

    second_response = auth_client.patch(f"/api/v1/todos/{second.todo_id}/complete/")
    assert second_response.status_code == 200
    assert Notification.objects.count() == 1

    notification = Notification.objects.get()
    assert notification.type == "reflection"
    assert notification.title == "오늘도 고생 많았어요"
    assert notification.content == "오늘 하루를 같이 정리 해볼까요?"
    assert notification.data["reflection_date"] == todo_date.isoformat()

    # 알림 생성 뒤 같은 날짜 TODO를 추가해 완료해도 새 알림을 만들지 않는다.
    added_later = Todo.objects.create(
        user=user, tag=tag, content="나중에 추가", todo_date=todo_date
    )
    third_response = auth_client.patch(f"/api/v1/todos/{added_later.todo_id}/complete/")
    assert third_response.status_code == 200
    assert Notification.objects.count() == 1


@pytest.mark.django_db
def test_midnight_tasks_fail_todos_and_send_reflection_notification(
    user: User,
    tag: Tag,
) -> None:
    # 자정 배치는 전날 미완료 TODO를 실패 처리한 뒤 회고 알림을 생성한다.
    target_date = timezone.localdate() - timedelta(days=1)
    Todo.objects.create(
        user=user,
        tag=tag,
        content="미완료",
        todo_date=target_date,
    )

    fail_incomplete_todos()
    send_reflection_notification()

    assert Todo.objects.get().status == Todo.Status.FAILED
    notification = Notification.objects.get(user=user)
    assert notification.type == "reflection"
    assert notification.data["reflection_date"] == target_date.isoformat()


@pytest.mark.django_db
def test_reflection_notification_skips_existing_reflection(
    user: User,
    tag: Tag,
) -> None:
    # 이미 회고를 작성한 날짜는 실패 TODO가 있어도 알림을 다시 만들지 않는다.
    target_date = timezone.localdate() - timedelta(days=1)
    Todo.objects.create(
        user=user,
        tag=tag,
        content="미완료",
        todo_date=target_date,
    )
    Reflection.objects.create(
        user=user,
        reflection_date=target_date,
        good_points="좋았던 점",
        improvement_points="아쉬운 점",
    )

    fail_incomplete_todos()
    send_reflection_notification()

    assert Notification.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_notification_api_lists_and_marks_read(
    auth_client: APIClient,
    user: User,
) -> None:
    # 알림 API는 내 알림만 최신순으로 보여주고 읽음 상태로 변경할 수 있다.
    notification = Notification.objects.create(
        user=user,
        type="reflection",
        title="회고",
        content="회고 작성",
        data={"target": "reflection", "reflection_date": "2026-06-02"},
    )
    other_user = User.objects.create_user(
        email="other@test.com",
        password="password123",
        user_name="다른유저",
        birth="2000-01-01",
    )
    Notification.objects.create(
        user=other_user,
        type="reflection",
        title="다른 회고",
        content="다른 사용자 알림",
        data={"target": "reflection", "reflection_date": "2026-06-02"},
    )

    list_response = auth_client.get("/api/v1/notifications/")
    assert list_response.status_code == 200
    notifications = list_response.json()
    assert len(notifications) == 1
    assert notifications[0]["notification_id"] == notification.notification_id

    read_response = auth_client.patch(
        f"/api/v1/notifications/{notification.notification_id}/read/"
    )
    assert read_response.status_code == 200
    notification.refresh_from_db()
    assert notification.is_read is True
