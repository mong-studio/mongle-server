# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read the shared project context first:

- `docs/setup-guide.md`

## Project Overview

`mongle-server` is a Django 5.2 LTS backend service using MySQL-compatible database configuration through `django-environ`.

Project documentation lives under `docs/`:

- `docs/setup-guide.md` - local setup, Make commands, Docker usage, and PR checks

## Commands

```bash
make install-dev
make migrate
make runserver
make docker-up
make docker-down
make lint
make format
make test
make typecheck
make ci-check
```

## Architecture

- `manage.py` - Django management entrypoint
- `config/` - Django project configuration, URLs, ASGI/WSGI, and split settings
- `apps/` - Django apps
- `common/` - shared utilities and base classes
- `infrastructure/` - third-party integrations
- `tests/` - pytest test suite
- `docker-compose.yml` - local Django + MySQL stack
- `.github/workflows/ci.yml` - GitHub Actions workflow

## Configuration

Use `.env.example` as the local environment template. RDS can be introduced later by replacing `DATABASE_URL`.

## Code Style

- Python 3.12+
- Ruff for linting and formatting
- mypy strict mode with `django-stubs`
- pytest + pytest-django for tests
