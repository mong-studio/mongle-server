FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY apps ./apps
COPY common ./common
COPY config ./config
COPY infrastructure ./infrastructure
COPY manage.py ./

RUN uv sync --locked --no-dev

EXPOSE 8000

# AI(generate/chat)는 요청 안에서 mongle-ai 를 최대 150s 동기 폴링한다. 동기 워커만 쓰면
# 워커 4개가 곧장 묶여(starvation) 다른 요청이 본문 없는 502 를 받는다. IO 대기 중 GIL 을
# 놓는 thread 워커로 동시성을 확보하고, timeout 은 AI 예산(150s) 위로 올린다.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "16", "--timeout", "180"]
