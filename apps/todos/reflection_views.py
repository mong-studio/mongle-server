from __future__ import annotations

from datetime import date
from typing import cast
import uuid

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.todos.models import Reflection, Todo
from apps.users.api_errors import error_response
from apps.users.models import TokenTransaction, User

REFLECTION_REWARD_PER_FIELD = 2
REFLECTION_REWARD_MIN_LENGTH = 30
REFLECTION_UPDATE_COST = 15
REFLECTION_MAX_LENGTH = 400
SYSTEM_FIELDS = {"reflection_id", "created_at", "updated_at"}
PATCH_FORBIDDEN_FIELDS = {"reflection_date", "created_at", "updated_at"}
APIResponse = Response | JsonResponse


class ReflectionContextView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request, date_text: str) -> APIResponse:
        reflection_date = _parse_date(date_text)
        if reflection_date is None:
            return error_response(400, "INVALID_REFLECTION_DATE")

        user = cast(User, request.user)
        todos = (
            Todo.objects.filter(user=user, todo_date=reflection_date)
            .select_related("tag")
            .order_by("created_at")
        )
        reflection = Reflection.objects.filter(
            user=user,
            reflection_date=reflection_date,
        ).first()
        payload: dict[str, object] = {
            "reflection_date": reflection_date.isoformat(),
            "completed_todos": [
                _serialize_todo(todo)
                for todo in todos
                if todo.status == Todo.Status.COMPLETED
            ],
            "incomplete_todos": [
                _serialize_todo(todo)
                for todo in todos
                if todo.status != Todo.Status.COMPLETED
            ],
            "already_reflected": reflection is not None,
        }
        if reflection is not None:
            payload["reflection"] = _serialize_reflection(reflection)
        return Response(payload)


class ReflectionCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> APIResponse:
        before_date = _parse_date(request.query_params.get("before"))
        if before_date is None:
            return error_response(400, "INVALID_REFLECTION_DATE")

        user = cast(User, request.user)
        reflections = Reflection.objects.filter(
            user=user,
            reflection_date__lt=before_date,
        ).order_by("reflection_date")
        return Response(
            [_serialize_reflection(reflection) for reflection in reflections]
        )

    def post(self, request: Request) -> APIResponse:
        if SYSTEM_FIELDS.intersection(request.data):
            return error_response(400, "SYSTEM_FIELD_NOT_ALLOWED")

        reflection_date = _parse_date(request.data.get("reflection_date"))
        if reflection_date is None or reflection_date > timezone.localdate():
            return error_response(400, "INVALID_REFLECTION_DATE")

        good_points = _validate_content(request.data.get("good_points"))
        improvement_points = _validate_content(request.data.get("improvement_points"))
        if good_points is None or improvement_points is None:
            return error_response(422, "INVALID_REFLECTION_CONTENT")

        request_user = cast(User, request.user)
        if Reflection.objects.filter(
            user=request_user,
            reflection_date=reflection_date,
        ).exists():
            return error_response(409, "REFLECTION_ALREADY_CONFIRMED")

        good_rewarded = len(good_points) >= REFLECTION_REWARD_MIN_LENGTH
        improvement_rewarded = len(improvement_points) >= REFLECTION_REWARD_MIN_LENGTH
        reward = (REFLECTION_REWARD_PER_FIELD if good_rewarded else 0) + (
            REFLECTION_REWARD_PER_FIELD if improvement_rewarded else 0
        )

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request_user.pk)
            reflection = Reflection.objects.create(
                user=user,
                reflection_date=reflection_date,
                good_points=good_points,
                improvement_points=improvement_points,
                good_token_rewarded=good_rewarded,
                improvement_token_rewarded=improvement_rewarded,
            )
            if reward:
                user.token_balance += reward
                user.save(update_fields=["token_balance", "updated_at"])
                TokenTransaction.objects.create(
                    user=user,
                    amount=reward,
                    type="reflection_reward",
                    reference_id=str(reflection.reflection_id),
                )

        payload = {
            "reflection_id": str(reflection.reflection_id),
            "reflection_date": reflection.reflection_date.isoformat(),
            "good_points": reflection.good_points,
            "improvement_points": reflection.improvement_points,
            "token": reward,
        }
        return Response(payload, status=status.HTTP_201_CREATED)


class ReflectionDateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request, date_text: str) -> APIResponse:
        reflection_date = _parse_date(date_text)
        if reflection_date is None:
            return error_response(400, "INVALID_REFLECTION_DATE")

        user = cast(User, request.user)
        reflection = Reflection.objects.filter(
            user=user,
            reflection_date=reflection_date,
        ).first()
        if reflection is None:
            return error_response(404, "REFLECTION_NOT_FOUND")
        return Response(_serialize_reflection(reflection))


class ReflectionDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request: Request, reflection_id: uuid.UUID) -> APIResponse:
        if PATCH_FORBIDDEN_FIELDS.intersection(request.data):
            return error_response(400, "FIELD_NOT_ALLOWED")

        good_points = _validate_content(request.data.get("good_points"))
        improvement_points = _validate_content(request.data.get("improvement_points"))
        if good_points is None or improvement_points is None:
            return error_response(422, "INVALID_REFLECTION_CONTENT")

        request_user = cast(User, request.user)
        with transaction.atomic():
            reflection = (
                Reflection.objects.select_for_update()
                .filter(
                    reflection_id=reflection_id,
                    user=request_user,
                )
                .first()
            )
            if reflection is None:
                return error_response(404, "REFLECTION_NOT_FOUND")

            user = User.objects.select_for_update().get(pk=request_user.pk)
            if user.token_balance < REFLECTION_UPDATE_COST:
                return error_response(402, "INSUFFICIENT_TOKEN_BALANCE")

            new_reward = 0
            if reflection.reflection_date == timezone.localdate():
                if (
                    not reflection.good_token_rewarded
                    and len(good_points) >= REFLECTION_REWARD_MIN_LENGTH
                ):
                    reflection.good_token_rewarded = True
                    new_reward += REFLECTION_REWARD_PER_FIELD
                if (
                    not reflection.improvement_token_rewarded
                    and len(improvement_points) >= REFLECTION_REWARD_MIN_LENGTH
                ):
                    reflection.improvement_token_rewarded = True
                    new_reward += REFLECTION_REWARD_PER_FIELD

            reflection.good_points = good_points
            reflection.improvement_points = improvement_points
            reflection.save(
                update_fields=[
                    "good_points",
                    "improvement_points",
                    "good_token_rewarded",
                    "improvement_token_rewarded",
                    "updated_at",
                ]
            )
            token_delta = new_reward - REFLECTION_UPDATE_COST
            user.token_balance += token_delta
            user.save(update_fields=["token_balance", "updated_at"])
            TokenTransaction.objects.create(
                user=user,
                amount=-REFLECTION_UPDATE_COST,
                type="reflection_update",
                reference_id=str(reflection.reflection_id),
            )
            if new_reward:
                TokenTransaction.objects.create(
                    user=user,
                    amount=new_reward,
                    type="reflection_reward",
                    reference_id=str(reflection.reflection_id),
                )

        return Response(
            {
                "reflection_id": str(reflection.reflection_id),
                "reflection_date": reflection.reflection_date.isoformat(),
                "good_points": reflection.good_points,
                "improvement_points": reflection.improvement_points,
                "reward": token_delta,
                "update_cost": REFLECTION_UPDATE_COST,
                "new_reward": new_reward,
                "token_delta": token_delta,
                "updated_at": reflection.updated_at.isoformat().replace("+00:00", "Z"),
            }
        )


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _validate_content(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    content = value.strip()
    if not content or len(content) > REFLECTION_MAX_LENGTH:
        return None
    return content


def _serialize_todo(todo: Todo) -> dict[str, object]:
    return {
        "todo_id": str(todo.todo_id),
        "content": todo.content,
        "status": todo.status,
        "todo_date": todo.todo_date.isoformat(),
        "tag_id": todo.tag_id,
        "tag_content": todo.tag.content if todo.tag else None,
        "tag_color": todo.tag.color if todo.tag else None,
    }


def _serialize_reflection(reflection: Reflection) -> dict[str, object]:
    return {
        "reflection_id": str(reflection.reflection_id),
        "reflection_date": reflection.reflection_date.isoformat(),
        "good_points": reflection.good_points,
        "improvement_points": reflection.improvement_points,
        "good_token_rewarded": reflection.good_token_rewarded,
        "improvement_token_rewarded": reflection.improvement_token_rewarded,
        "created_at": reflection.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": reflection.updated_at.isoformat().replace("+00:00", "Z"),
    }
