# Redis 로컬 설정 가이드

## 개요

이 프로젝트에서 Redis는 **Celery 메시지 브로커 + 결과 저장소**로 사용됩니다.  
Django 캐시로는 사용하지 않습니다.

---

## 1. Redis 설치

### macOS
```bash
brew install redis
brew services start redis   # 백그라운드 자동 실행
```

### Ubuntu / Debian
```bash
sudo apt update && sudo apt install redis-server
sudo systemctl enable --now redis
```

### Docker (별도 설치 없이)
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

---

## 2. 환경변수 설정

`.env` 파일에 아래 항목이 있는지 확인합니다.

```bash
REDIS_URL=redis://localhost:6379/0
```

기본값이 `localhost:6379/0`이므로 로컬에서는 그대로 사용하면 됩니다.

---

## 3. 로컬 실행 (프로세스 3개 필요)

터미널을 3개 열어 각각 실행합니다.

```bash
# 터미널 1 — Django 웹 서버
make runserver

# 터미널 2 — Celery 워커 (실제 작업 실행)
celery -A config worker -l info

# 터미널 3 — Celery Beat (스케줄 트리거)
celery -A config beat -l info
```

---

## 4. Docker Compose로 실행

`docker-compose.yml`에 Redis가 포함되어 있으므로 아래 명령 하나로 전부 뜹니다.

```bash
make docker-up
```

단, **Celery 워커/비트는 docker-compose에 포함되어 있지 않습니다.**  
스케줄 작업이나 지연 실행이 필요하면 위 3번처럼 별도로 실행해야 합니다.

---

## 5. Celery 작업 목록

### 스케줄 작업 (매일 자정 자동 실행)

| 실행 시각 | 작업 | 설명 |
|---|---|---|
| 00:00 | `todos.tasks.fail_incomplete_todos` | 미완료 TODO → FAILED 처리 |
| 00:01 | `users.tasks.send_reflection_notification` | 전날 실패 TODO가 있는 유저에게 회고 알림 발송 |
| 00:02 | `characters.tasks.reset_image_gen_count` | 이미지 생성 횟수 초기화 |

### 이벤트 트리거 작업

| 트리거 | 작업 | 설명 |
|---|---|---|
| 댓글 작성 | `posts.tasks.generate_character_reply` | 10분 후 캐릭터 자동 답글 생성 |

---

## 6. 동작 확인

Redis 연결 확인:
```bash
redis-cli ping   # PONG 이 출력되면 정상
```

Celery 워커에서 작업 수동 실행 (테스트용):
```bash
python manage.py shell
>>> from apps.todos.tasks import fail_incomplete_todos
>>> fail_incomplete_todos.delay()
```
