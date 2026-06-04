from django.urls import path

from apps.users.views import LoginView, MeView, TokenRefreshView

urlpatterns = [
    path("login", LoginView.as_view(), name="auth-login"),
    path("token/refresh", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
]
