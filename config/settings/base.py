"""Shared Django settings."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import environ

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parents[2]

# django-environ: .env 파일에서 환경변수를 읽어오는 라이브러리
# 형식: 변수명=(타입, 기본값)
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, "unsafe-development-secret-key"),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    EMAIL_HOST=(str, ""),
    EMAIL_PORT=(int, 587),
    EMAIL_USE_TLS=(bool, True),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    DEFAULT_FROM_EMAIL=(str, "noreply@mongle.local"),
)


environ.Env.read_env(BASE_DIR / ".env")
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    # Django 기본 앱 (건드리지 않음)
    "django.contrib.admin",  # /admin 관리자 페이지
    "django.contrib.auth",  # 인증 시스템 (로그인, 비밀번호 등)
    "django.contrib.contenttypes",  # 모델 타입 추적
    "django.contrib.sessions",  # 세션 관리
    "django.contrib.messages",  # 일회성 메시지 (플래시 메시지)
    "django.contrib.staticfiles",  # 정적 파일 (CSS, JS 등) 관리
    # 외부 패키지
    "rest_framework",
    "rest_framework_simplejwt",
    "django_celery_beat",
    # 추가 앱
    "apps.users",  # 회원/인증
    "apps.characters",  # 캐릭터
    "apps.todos",  # TODO
    "apps.quests",  # 퀘스트
    "apps.posts",  # 피드/댓글
]

MIDDLEWARE = [
    # 모든 요청/응답을 처리하는 중간 계층 (순서가 중요)
    "django.middleware.security.SecurityMiddleware",  # 보안 헤더 추가
    "django.contrib.sessions.middleware.SessionMiddleware",  # 세션 처리
    "django.middleware.common.CommonMiddleware",  # URL 슬래시 처리 등
    "django.middleware.csrf.CsrfViewMiddleware",  # CSRF 공격 방어
    "django.contrib.auth.middleware.AuthenticationMiddleware",  # 요청에서 유저 식별
    "django.contrib.messages.middleware.MessageMiddleware",  # 메시지 처리
    "django.middleware.clickjacking.XFrameOptionsMiddleware",  # 클릭재킹 방어
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"  # 배포 서버 연결 설정

# 데이터베이스 설정: DATABASE_URL 환경변수에서 읽어오고, 없으면 SQLite 사용
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    ),
}

VALIDATOR_MODULE = "django.contrib.auth.password_validation"
AUTH_PASSWORD_VALIDATORS = [
    # 비밀번호 규칙 검증 목록
    {
        "NAME": f"{VALIDATOR_MODULE}.UserAttributeSimilarityValidator"
    },  # 이름과 비슷한 비밀번호 금지
    {"NAME": f"{VALIDATOR_MODULE}.MinimumLengthValidator"},  # 최소 길이 검사
    {"NAME": f"{VALIDATOR_MODULE}.CommonPasswordValidator"},  # 너무 흔한 비밀번호 금지
    {
        "NAME": f"{VALIDATOR_MODULE}.NumericPasswordValidator"
    },  # 숫자로만 된 비밀번호 금지
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
EMAIL_BACKEND = env("EMAIL_BACKEND")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

AUTH_USER_MODEL = "users.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        # 모든 API의 기본 인증 방식: 요청 헤더의 JWT 토큰을 검증
        # 헤더 형식: Authorization: Bearer <토큰값>
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        # 기본적으로 로그인한 사람만 API 사용 가능
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(weeks=2),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "user_id",
    "USER_ID_CLAIM": "user_id",
}


REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = "Asia/Seoul"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "fail-incomplete-todos": {
        "task": "apps.todos.tasks.fail_incomplete_todos",
        "schedule": crontab(hour=0, minute=0),
    },
    "send-reflection-notification": {
        "task": "apps.users.tasks.send_reflection_notification",
        "schedule": crontab(hour=0, minute=1),
    },
    "reset-image-gen-count": {
        "task": "apps.characters.tasks.reset_image_gen_count",
        "schedule": crontab(hour=0, minute=2),
    },
}
