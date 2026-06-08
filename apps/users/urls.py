from django.urls import path

from apps.users.views import LoginView, LogoutView, MeView, RefreshView

urlpatterns = [
    path("login", LoginView.as_view(), name="auth-login"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("token/refresh", RefreshView.as_view(), name="auth-token-refresh"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
]
