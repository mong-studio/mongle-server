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

프로젝트 설명은 [docs/README.md](docs/README.md)에 정리되어 있습니다.

팀원, Codex, Claude가 함께 보는 공통 컨텍스트는 [docs/shared-context.md](docs/shared-context.md)에 있습니다.
