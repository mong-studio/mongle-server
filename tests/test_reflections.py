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
def test_todo_complete_creates_reflection_notification_once(
    auth_client: APIClient,
    user: User,
    tag: Tag,
) -> None:
    # 마지막 남은 TODO를 완료했을 때만 당일 회고 알림을 한 번 생성한다.
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
    assert notification.data["reflection_date"] == todo_date.isoformat()


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
