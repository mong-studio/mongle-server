# Mongle Server 세팅 가이드

이 문서는 프로젝트 설치, `.venv` 생성, 서버 실행, Make 명령어를 설명합니다.

프로젝트 구조와 개발 원칙은 [project-guide.md](project-guide.md)를 확인해 주세요.
Git과 PR 방법은 [git-strategy.md](git-strategy.md)를 확인해 주세요.
데이터베이스 상세 세팅은 [database-guide.md](database-guide.md)를 확인해 주세요.

## 로컬 Python 환경

프로젝트를 처음 받았다면 아래 순서대로 실행합니다.

```bash
cp .env.example .env
make install-dev
make migrate
make runserver
```

`make install-dev`는 `uv`를 사용해 프로젝트 루트에 `.venv` 가상환경을 만들고 개발 의존성을 설치합니다.
따라서 보통은 `python -m venv .venv`를 따로 실행하지 않아도 됩니다.

가상환경이 만들어졌는지 확인하고 싶다면 아래 명령어를 실행합니다.

```bash
ls .venv
```

터미널에서 직접 가상환경을 활성화하고 싶을 때는 아래 명령어를 사용합니다.

```bash
source .venv/bin/activate
```

서버 실행 후 다른 터미널에서 헬스 체크를 합니다.

```bash
curl http://localhost:8000/health/
```

success:

```json
{ "status": "ok" }
```

## Docker로 실행하기

Docker 사용 시 Django 서버와 MySQL 서버를 함께 띄워 줍니다.

```bash
cp .env.example .env
make docker-up
```

Docker 종료 시 다음과 같습니다.

```bash
make docker-down
```

Docker 실행 중 서버 로그를 보고 싶을 때는 아래 명령어를 씁니다.

```bash
make docker-logs
```

## 명령어 치트시트

| 명령어               | 무엇을 하나요?                                              | 언제 쓰나요?                         |
| -------------------- | ----------------------------------------------------------- | ------------------------------------ |
| `make help`          | 사용 가능한 명령어 목록을 보여줍니다.                       | 무슨 명령어가 있는지 까먹었을 때     |
| `make install-dev`   | 개발에 필요한 패키지를 설치하고 Git 훅을 연결합니다.        | 처음 세팅할 때                       |
| `make install-hooks` | Git `pre-commit`, `commit-msg`, `pre-push` 훅을 설치합니다. | 훅만 다시 연결하고 싶을 때           |
| `make migrate`       | 데이터베이스 구조를 최신 상태로 맞춥니다.                   | 처음 실행하거나 DB 변경 뒤           |
| `make runserver`     | Django 개발 서버를 8000번 포트로 실행합니다.                | 로컬에서 API를 확인할 때             |
| `make shell`         | Django shell을 엽니다.                                      | 데이터나 설정을 직접 확인할 때       |
| `make lint`          | Ruff가 코드 문제를 찾고 고칠 수 있는 것은 고칩니다.         | 커밋 전 코드 정리                    |
| `make format`        | 코드 모양을 프로젝트 규칙에 맞춥니다.                       | 커밋 전 코드 정리                    |
| `make test`          | pytest와 coverage를 실행합니다.                             | 내 변경이 망가뜨린 것이 없는지 볼 때 |
| `make typecheck`     | mypy 타입 검사를 실행합니다.                                | 타입 관련 실수를 찾을 때             |
| `make validate`      | lint, format, test, typecheck를 한 번에 실행합니다.         | 전체 검증을 하고 싶을 때             |
| `make ci-check`      | GitHub Actions와 비슷한 전체 검사를 실행합니다.             | CI와 비슷하게 확인하고 싶을 때       |
| `make docker-up`     | Docker compose로 `web`과 `db`를 실행합니다.                 | Docker 환경으로 실행할 때            |
| `make docker-down`   | Docker compose로 띄운 컨테이너를 종료합니다.                | Docker 환경을 멈출 때                |
| `make docker-logs`   | `web` 컨테이너 로그를 계속 보여줍니다.                      | Docker 실행 중 문제를 볼 때          |
