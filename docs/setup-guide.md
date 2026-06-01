# Mongle Server 안내서

## 실행 방법(간단)

로컬 Python 환경에서 실행 시에는 다음과 같습니다.

```bash
cp .env.example .env
make install-dev
make migrate
make runserver
```

서버 실행 후 다른 터미널에서 헬스 체크를 합니다.

```bash
curl http://localhost:8000/health/
```

succss:

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

## 초기 세팅

1. 프로젝트 폴더로 이동
2. `.env.example` 파일을 `.env`로 복사합니다.
3. 개발 도구를 설치합니다.
4. 데이터베이스 마이그레이션을 실행합니다.
5. 서버를 켭니다.
6. 헬스체크 주소로 접속하여 서버가 살아있는지 확인합니다.

각 단계의 명령어는 아래와 같습니다.

```bash
cp .env.example .env
make install-dev
make migrate
make runserver
curl http://localhost:8000/health/
```

## 명령어 치트시트

| 명령어             | 무엇을 하나요?                                       | 언제 쓰나요?                         |
| ------------------ | ---------------------------------------------------- | ------------------------------------ |
| `make help`        | 사용 가능한 명령어 목록을 보여줍니다.                | 무슨 명령어가 있는지 까먹었을 때     |
| `make install-dev` | 개발에 필요한 패키지를 설치하고 Git 훅을 연결합니다. | 처음 세팅할 때                       |
| `make install-hooks` | Git `pre-commit`, `commit-msg`, `pre-push` 훅을 설치합니다. | 훅만 다시 연결하고 싶을 때 |
| `make migrate`     | 데이터베이스 구조를 최신 상태로 맞춥니다.            | 처음 실행하거나 DB 변경 뒤           |
| `make runserver`   | Django 개발 서버를 8000번 포트로 실행합니다.         | 로컬에서 API를 확인할 때             |
| `make shell`       | Django shell을 엽니다.                               | 데이터나 설정을 직접 확인할 때       |
| `make lint`        | Ruff가 코드 문제를 찾고 고칠 수 있는 것은 고칩니다.  | 커밋 전 코드 정리                    |
| `make format`      | 코드 모양을 프로젝트 규칙에 맞춥니다.                | 커밋 전 코드 정리                    |
| `make test`        | pytest와 coverage를 실행합니다.                      | 내 변경이 망가뜨린 것이 없는지 볼 때 |
| `make typecheck`   | mypy 타입 검사를 실행합니다.                         | 타입 관련 실수를 찾을 때             |
| `make validate`    | lint, format, test, typecheck를 한 번에 실행합니다.  | PR 올리기 전 최종 확인               |
| `make ci-check`    | GitHub Actions와 비슷한 전체 검사를 실행합니다.      | CI 실패를 미리 줄이고 싶을 때        |
| `make docker-up`   | Docker compose로 `web`과 `db`를 실행합니다.          | Docker 환경으로 실행할 때            |
| `make docker-down` | Docker compose로 띄운 컨테이너를 종료합니다.         | Docker 환경을 멈출 때                |
| `make docker-logs` | `web` 컨테이너 로그를 계속 보여줍니다.               | Docker 실행 중 문제를 볼 때          |

## PR 올리기 전 체크

`make install-dev` 또는 `make install-hooks`를 실행하면 로컬 Git 훅이 설치됩니다.

- `pre-commit`: Ruff lint 자동 수정과 format을 실행합니다.
- `commit-msg`: Commitizen 규칙으로 커밋 메시지를 검사합니다.
- `pre-push`: `make ci-check`로 CI와 비슷한 전체 검사를 실행합니다.

PR을 올리기 전에 아래 명령어를 한 번 실행하면 좋습니다.

```bash
make validate
```

이 명령어는 아래 검사를 한 번에 실행합니다.

- `make lint`
- `make format`
- `make test`
- `make typecheck`

CI와 최대한 비슷하게 확인하고 싶으면 아래 명령어를 사용합니다.

```bash
make ci-check
```

## 폴더 구조

| 폴더              | 쉬운 설명                                                         |
| ----------------- | ----------------------------------------------------------------- |
| `config/`         | Django 설정과 URL 입구가 있는 곳입니다.                           |
| `apps/`           | 우리가 만드는 Django 앱이 들어가는 곳입니다.                      |
| `common/`         | 여러 앱이 같이 쓰는 공통 코드가 들어가는 곳입니다.                |
| `infrastructure/` | 이메일, 저장소처럼 바깥 서비스와 가까운 코드가 들어가는 곳입니다. |
| `tests/`          | 테스트 코드가 들어가는 곳입니다.                                  |
| `docs/`           | 팀원이 읽는 문서가 들어가는 곳입니다.                             |
