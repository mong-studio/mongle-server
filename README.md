# Mongle Server

Django 5.2 LTS와 MySQL을 사용하는 Mongle 백엔드 서버입니다.

## 빠른 시작

로컬 Python 환경:

```bash
cp .env.example .env
make install-dev
make migrate
make runserver
```

Docker 환경:

```bash
cp .env.example .env
make docker-up
```

헬스체크:

```bash
curl http://localhost:8000/health/
```

## 문서

- 전체 문서 안내는 [docs/README.md](docs/README.md)에 있습니다.
- 프로젝트 구조와 개발 원칙은 [docs/project-guide.md](docs/project-guide.md)에 있습니다.
- Git 전략과 PR 작성 방법은 [docs/git-strategy.md](docs/git-strategy.md)에 있습니다.
- 로컬 세팅, Make 명령어, Docker 사용법은 [docs/setup-guide.md](docs/setup-guide.md)에 있습니다.
- 데이터베이스 설정과 운영 참고사항은 [docs/database-guide.md](docs/database-guide.md)에 있습니다.
