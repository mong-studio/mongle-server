"""Production settings."""

import environ

from .base import *  # noqa: F403

_env = environ.Env()

SECRET_KEY = _env("DJANGO_SECRET_KEY")

DATABASES = {
    "default": _env.db("DATABASE_URL"),
}

DEBUG = False

REDIS_URL = _env("REDIS_URL")

ALLOWED_HOSTS = _env.list("DJANGO_ALLOWED_HOSTS")

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
