from django.urls import path

from apps.users.social_views import KakaoCompleteView, KakaoLoginView
from apps.users.views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    WithdrawView,
)

urlpatterns = [
    path("login", LoginView.as_view(), name="auth-login"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("token/refresh", RefreshView.as_view(), name="auth-token-refresh"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("withdraw", WithdrawView.as_view(), name="auth-withdraw"),
    path("social/kakao", KakaoLoginView.as_view(), name="auth-social-kakao"),
    path(
        "social/kakao/complete",
        KakaoCompleteView.as_view(),
        name="auth-social-kakao-complete",
    ),
]
