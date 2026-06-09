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
    # 브라우저에서 직접 호출을 허용할 프론트엔드 origin 목록.
    # 형식: scheme://host[:port] (쉼표로 구분). dev 기본값은 로컬 프론트.
    DJANGO_CORS_ALLOWED_ORIGINS=(
        list,
        ["http://localhost:3000", "http://localhost:5173"],
    ),
    MONGLE_AI_API_BASE=(str, "http://127.0.0.1:8010"),
    MONGLE_AI_API_KEY=(str, ""),
    MONGLE_AI_TIMEOUT_SECONDS=(float, 15.0),
)


environ.Env.read_env(BASE_DIR / ".env")
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# CORS: 브라우저가 다른 origin에서 이 API를 호출할 수 있는 화이트리스트.
# refresh token을 HttpOnly 쿠키로 cross-origin 흐름(로그인/재발급/로그아웃)에서
# 주고받으므로 CORS_ALLOW_CREDENTIALS=True가 필요하다. 이 값이 없으면 브라우저가
# credentialed 요청에서 Set-Cookie를 저장하지 않고 쿠키도 전송하지 않는다.
# (프론트는 fetch에 credentials: "include"를 함께 보내야 한다.)
# 기본 CORS_ALLOW_HEADERS에 "authorization"이 포함되어 Bearer 토큰 전송도 가능.
CORS_ALLOWED_ORIGINS = env("DJANGO_CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

INSTALLED_APPS = [
    # Django 기본 앱 (건드리지 않음)
    "django.contrib.admin",  # /admin 관리자 페이지
    "django.contrib.auth",  # 인증 시스템 (로그인, 비밀번호 등)
    "django.contrib.contenttypes",  # 모델 타입 추적
    "django.contrib.sessions",  # 세션 관리
    "django.contrib.messages",  # 일회성 메시지 (플래시 메시지)
    "django.contrib.staticfiles",  # 정적 파일 (CSS, JS 등) 관리
    # 외부 패키지
    "corsheaders",  # 브라우저 cross-origin 요청(CORS) 헤더 처리
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
    "corsheaders.middleware.CorsMiddleware",  # CORS 헤더 추가 (CommonMiddleware보다 위)
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

# 캐시: 레이트 리밋 카운터 등을 여러 워커 프로세스 간에 공유하기 위해 Redis 사용.
# (Django 기본 LocMemCache는 프로세스별이라 멀티워커에서 카운트가 분산된다.)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    },
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = "Asia/Seoul"
MONGLE_AI_API_BASE = env("MONGLE_AI_API_BASE")
MONGLE_AI_API_KEY = env("MONGLE_AI_API_KEY")
MONGLE_AI_TIMEOUT_SECONDS = env("MONGLE_AI_TIMEOUT_SECONDS")
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
    "cleanup-expired-refresh-tokens": {
        "task": "apps.users.tasks.cleanup_expired_refresh_tokens",
        "schedule": crontab(hour=0, minute=3),
    },
}
