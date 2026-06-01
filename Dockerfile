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

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
