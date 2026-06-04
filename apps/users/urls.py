from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView,  # simplejwt가 제공하는 토큰 갱신 View
)

from apps.users.views import LoginView, MeView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
]
