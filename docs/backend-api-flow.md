# Backend API Flow

이 문서는 `mongle-server`가 프론트엔드(`mongle-web`)와 AI 서버(`mongle-ai`) 사이에서 API를 어떻게 중계하고 저장하는지 정리한다.

## 기본 원칙

- 브라우저는 내부 서비스 토큰을 알면 안 된다.
- 프론트엔드가 호출하는 Django API는 `Authorization: Bearer {access_token}` 기반으로 인증한다.
- Django가 AI 서버를 호출할 때는 내부 헤더를 붙인다.
- AI 공통 규칙상 내부 API는 `X-Internal-Service-Token`을 검증해야 한다.
- DB 저장은 Django가 담당한다.

## 공통 헤더

### Web -> Django

| Header | 설명 |
| --- | --- |
| `Authorization: Bearer {access_token}` | 로그인 사용자 인증 |
| `Content-Type: application/json` | JSON 요청 |
| `X-Client-Type` | 클라이언트 구분 |
| `X-Client-Version` | 클라이언트 버전 |

### Django -> AI

| Header | 설명 |
| --- | --- |
| `X-Internal-Service-Token` | 내부 서비스 토큰 |
| `X-API-Key` | 기존 AI 구현 호환용 API key |
| `X-Request-Id` | 요청 추적 ID |
| `Content-Type: application/json` | JSON 요청 |

## TODO 플래너 흐름

### 1. 멀티턴 대화

```text
mongle-web
  POST /api/v1/todos/chat/
    Authorization: Bearer {access_token}

mongle-server
  POST {MONGLE_AI_API_BASE}/v1/todo/chat
    X-Internal-Service-Token: {MONGLE_AI_API_KEY}
    X-API-Key: {MONGLE_AI_API_KEY}

mongle-ai
  follow_up 또는 candidates 반환
```

프론트는 `/todos/chat/` 응답이 `follow_up`이면 같은 `thread_id`로 대화를 이어가고, `candidates`이면 생성된 계획을 화면에 보여준다.

### 2. 프론트 플래너 저장

```text
mongle-web
  POST /api/v1/todos/planner-confirm/
    Authorization: Bearer {access_token}

mongle-server
  현재 로그인 사용자 기준으로 Todo/Schedule 저장
  오늘 날짜 Todo가 있으면 quest 생성 시도

mongle-ai
  POST /v1/quest/generate
    X-Internal-Service-Token: {MONGLE_AI_API_KEY}
    X-API-Key: {MONGLE_AI_API_KEY}
```

`/todos/planner-confirm/`은 브라우저에서 호출하는 저장 API다. 내부 서비스 토큰을 요구하지 않고, 저장 대상 사용자는 `request.user`다.

저장 시 후보는 날짜 기준으로 다시 분류한다.

| 조건 | 저장 위치 |
| --- | --- |
| `due_date == 오늘` | `Todo` |
| `due_date != 오늘` | `Schedule` |

### 3. AI 내부 commit

```text
internal caller
  POST /api/v1/todos/commit/
    X-Internal-Service-Token: {MONGLE_AI_API_KEY}

mongle-server
  내부 토큰 검증 후 Todo/Schedule 저장
```

`/todos/commit/`은 AI/internal 계약을 위해 남겨둔 endpoint다. 프론트에서 직접 호출하지 않는다.

현재 Django 구현에서는 인증 사용자 없이 내부 토큰만으로 들어오면 `demo@mongle.local` 사용자로 저장하는 fallback이 있다. 실제 사용자별 AI callback 저장을 사용하려면 요청 payload에 `user_id`를 포함하거나 `thread_id -> user` 매핑을 통해 저장 대상을 명확히 해야 한다.

## TODO 관련 endpoint 구분

| Endpoint | 호출자 | 인증 | 역할 |
| --- | --- | --- | --- |
| `POST /api/v1/todos/generate/` | Web | `Authorization` | 싱글턴 TODO 후보 생성 |
| `POST /api/v1/todos/chat/` | Web | `Authorization` | 멀티턴 플래너 대화 |
| `POST /api/v1/todos/planner-confirm/` | Web | `Authorization` | 플래너 후보를 현재 사용자 Todo/Schedule로 저장 |
| `POST /api/v1/todos/confirm/` | Web | `Authorization` | 일반 TODO 후보 확정 저장 |
| `POST /api/v1/todos/commit/` | Internal/AI | `X-Internal-Service-Token` | 내부 commit 계약 |

## AI 서버 endpoint 구분

| AI endpoint | Django 호출 위치 | 역할 |
| --- | --- | --- |
| `POST /v1/todo/generate` | `TodoAIClient.generate()` | 싱글턴 후보 생성 |
| `POST /v1/todo/chat` | `TodoAIClient.chat()` | 플래너 멀티턴 대화 |
| `POST /v1/todo/commit` | 현재 Django에서 직접 사용하지 않음 | AI 내부 commit 그래프 |
| `POST /v1/quest/generate` | `_assign_quests_to_todos()` | 저장된 오늘 Todo에 퀘스트 분배 |

## 주의사항

- `/todos/commit/`과 AI의 `/v1/todo/commit`은 이름이 비슷하지만 호출 방향과 책임을 반드시 확인해야 한다.
- 프론트는 `/todos/commit/`을 직접 호출하지 않고 `/todos/planner-confirm/`을 사용한다.
- AI 공통 규칙의 primary 내부 인증 헤더는 `X-Internal-Service-Token`이다.
- 기존 구현 호환을 위해 Django `TodoAIClient`는 `X-API-Key`도 함께 보낸다.
