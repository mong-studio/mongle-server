from django.urls import path

from apps.users.views import LoginView, MeView, RegisterView, TokenRefreshView

urlpatterns = [
    path("login", LoginView.as_view(), name="auth-login"),
    path("token/refresh", TokenRefreshView.as_view(), name="auth-refresh"),
]
