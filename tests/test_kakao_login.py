from datetime import date

import pytest

from apps.users.models import User
from apps.users.serializers import UserSerializer


@pytest.mark.django_db
def test_user_serializer_includes_login_type():
    user = User.objects.create_user(
        email="a@example.com",
        password="Passw0rd!",
        user_name="민지",
        birth=date(2000, 1, 1),
    )
    data = UserSerializer(user).data
    assert data["login_type"] == "email"
    assert "login_type" in data
