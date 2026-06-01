# ============================================================================
# Makefile - Django + MySQL backend automation
# ============================================================================

COLOR_RESET   := \033[0m
COLOR_BOLD    := \033[1m
COLOR_GREEN   := \033[32m
COLOR_YELLOW  := \033[33m
COLOR_BLUE    := \033[34m
COLOR_CYAN    := \033[36m

PYTHON ?= python3
VENV := .venv
VENV_BIN := $(VENV)/bin
PIP := $(VENV_BIN)/pip
PYTHON_VENV := $(VENV_BIN)/python

SRC_DIR := src
TEST_DIR := tests
ALL_DIRS := $(SRC_DIR) $(TEST_DIR) manage.py

RUFF := $(VENV_BIN)/ruff
PRE_COMMIT := $(VENV_BIN)/pre-commit
COMMITIZEN := $(VENV_BIN)/cz
MYPY := $(VENV_BIN)/mypy
PYTEST := $(VENV_BIN)/pytest
MANAGE := $(PYTHON_VENV) manage.py

.DEFAULT_GOAL := help

.PHONY: help install install-dev install-hooks clean lint format check \
        ci-check validate test typecheck migrate runserver shell \
        docker-up docker-down docker-logs pre-commit run-all commit \
        bump-version update-hooks

help:
	@echo "$(COLOR_BOLD)$(COLOR_CYAN)사용 가능한 Make 명령어:$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_GREEN)설치:$(COLOR_RESET)"
	@echo "  make install         - 프로덕션 의존성 설치"
	@echo "  make install-dev     - 개발 의존성 설치"
	@echo "  make install-hooks   - Git 훅 설치"
	@echo "  make clean           - 캐시 정리"
	@echo ""
	@echo "$(COLOR_GREEN)Django:$(COLOR_RESET)"
	@echo "  make migrate         - 데이터베이스 마이그레이션"
	@echo "  make runserver       - Django 개발 서버 실행"
	@echo "  make shell           - Django shell 실행"
	@echo ""
	@echo "$(COLOR_GREEN)검증:$(COLOR_RESET)"
	@echo "  make lint            - Ruff lint 자동 수정"
	@echo "  make format          - Ruff format"
	@echo "  make test            - pytest + coverage"
	@echo "  make typecheck       - mypy 타입 검사"
	@echo "  make check           - lint + format"
	@echo "  make validate        - lint + format + test + typecheck"
	@echo "  make ci-check        - CI용 전체 검사"
	@echo ""
	@echo "$(COLOR_GREEN)Docker:$(COLOR_RESET)"
	@echo "  make docker-up       - Docker compose 실행"
	@echo "  make docker-down     - Docker compose 종료"
	@echo "  make docker-logs     - web 컨테이너 로그 보기"
	@echo ""
	@echo "$(COLOR_GREEN)Git:$(COLOR_RESET)"
	@echo "  make commit          - Commitizen 대화형 커밋"
	@echo "  make bump-version    - 버전 증가 및 태그 생성"

install:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)프로덕션 의존성 설치 중...$(COLOR_RESET)"
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(PIP) install --upgrade pip setuptools wheel
	@$(PIP) install -e .
	@echo "$(COLOR_GREEN)✓ 설치 완료$(COLOR_RESET)"

install-dev:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)개발 의존성 설치 중...$(COLOR_RESET)"
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(PIP) install --upgrade pip setuptools wheel
	@$(PIP) install -e ".[dev]"
	@$(MAKE) install-hooks
	@echo "$(COLOR_GREEN)✓ 개발 환경 설치 완료$(COLOR_RESET)"

install-hooks:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)Git 훅 설치 중...$(COLOR_RESET)"
	@if [ -d .git ]; then \
		$(PRE_COMMIT) install --hook-type pre-commit; \
		$(PRE_COMMIT) install --hook-type commit-msg; \
		$(PRE_COMMIT) install --hook-type pre-push; \
		echo "$(COLOR_GREEN)✓ Git 훅 설치 완료$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_YELLOW)Git 저장소가 아니므로 훅 설치를 건너뜁니다.$(COLOR_RESET)"; \
	fi

clean:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)캐시 정리 중...$(COLOR_RESET)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .coverage .pytest_cache .mypy_cache .ruff_cache build dist htmlcov 2>/dev/null || true
	@echo "$(COLOR_GREEN)✓ 정리 완료$(COLOR_RESET)"

lint:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)Ruff lint 실행 중...$(COLOR_RESET)"
	@$(RUFF) check $(ALL_DIRS) --fix
	@echo "$(COLOR_GREEN)✓ lint 완료$(COLOR_RESET)"

format:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)Ruff format 실행 중...$(COLOR_RESET)"
	@$(RUFF) format $(ALL_DIRS)
	@echo "$(COLOR_GREEN)✓ format 완료$(COLOR_RESET)"

check: lint format
	@echo "$(COLOR_GREEN)✓ 코드 스타일 검사 통과$(COLOR_RESET)"

validate: lint format test typecheck
	@echo "$(COLOR_GREEN)✓ 전체 검증 통과$(COLOR_RESET)"

ci-check:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)CI 검사 실행 중...$(COLOR_RESET)"
	@$(RUFF) check $(ALL_DIRS) --no-fix
	@$(RUFF) format $(ALL_DIRS) --check
	@$(MANAGE) check
	@$(MANAGE) makemigrations --check --dry-run
	@$(MYPY) $(SRC_DIR)
	@$(PYTEST) --cov=src/mongle_server --cov-report=term-missing --no-header -q
	@echo "$(COLOR_GREEN)✓ CI 검사 통과$(COLOR_RESET)"

test:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)테스트 실행 중...$(COLOR_RESET)"
	@$(PYTEST) --cov=src/mongle_server --cov-report=term-missing
	@echo "$(COLOR_GREEN)✓ 테스트 완료$(COLOR_RESET)"

typecheck:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)타입 검사 중...$(COLOR_RESET)"
	@$(MYPY) $(SRC_DIR)
	@echo "$(COLOR_GREEN)✓ 타입 검사 완료$(COLOR_RESET)"

migrate:
	@$(MANAGE) migrate

runserver:
	@$(MANAGE) runserver 0.0.0.0:8000

shell:
	@$(MANAGE) shell

docker-up:
	@docker compose up --build

docker-down:
	@docker compose down

docker-logs:
	@docker compose logs -f web

pre-commit:
	@$(PRE_COMMIT) run

run-all:
	@$(PRE_COMMIT) run --all-files

commit:
	@$(COMMITIZEN) commit

bump-version:
	@$(COMMITIZEN) bump --yes

update-hooks:
	@$(PRE_COMMIT) autoupdate
