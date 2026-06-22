# TODO 보상·회고·알림 API 변경 명세

> 기준일: 2026-06-22  
> 대상: `mongle-web` ↔ `mongle-server` 회고, TODO 완료 보상, 알림 연동

## 공통 사항

- API prefix: `/api/v1`
- 인증: 모든 API는 로그인된 사용자만 호출할 수 있다.
- 날짜 형식: `YYYY-MM-DD`
- 날짜와 알림 데이터는 요청한 사용자 소유 데이터만 조회하거나 변경한다.
- 공통 에러 응답은 다음 형식을 사용한다.

```json
{
  "error": {
    "code": 400,
    "message": "INVALID_REFLECTION_DATE",
    "details": {}
  }
}
```

## 변경 요약

| 구분 | 메서드 | 경로 | 변경 내용 |
| --- | --- | --- | --- |
| 신규 | `GET` | `/api/v1/reflections/?before={date}` | 기준일 이전 회고 목록 조회 |
| 변경 | `PATCH` | `/api/v1/reflections/{reflection_id}/` | 수정 보상 계산 및 응답 필드 확장 |
| 변경 | `PATCH` | `/api/v1/todos/{todo_id}/complete/` | TODO 보상 지급 및 서버 잔액 반환 |
| 연동 | `GET` | `/api/v1/notifications/` | 서버 알림 목록 조회 |
| 연동 | `PATCH` | `/api/v1/notifications/{notification_id}/read/` | 알림 읽음 처리 |

## 1. 이전 회고 목록 조회

기준일보다 이전에 작성한 본인의 회고를 날짜 오름차순으로 반환한다. 기준일 당일의 회고는 포함하지 않는다.

### 요청

```http
GET /api/v1/reflections/?before=2026-06-22
```

| Query | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `before` | string | O | 조회 기준일. 해당 날짜 미포함 |

### 성공 응답

`200 OK`

```json
[
  {
    "reflection_id": "a9fa4138-9ab3-4aba-ae4c-6cce90aa4f47",
    "reflection_date": "2026-06-20",
    "good_points": "계획한 운동을 끝까지 마쳤어요.",
    "improvement_points": "휴식 시간을 충분히 챙기지 못했어요.",
    "good_token_rewarded": true,
    "improvement_token_rewarded": true,
    "created_at": "2026-06-20T12:30:00Z",
    "updated_at": "2026-06-20T12:30:00Z"
  }
]
```

회고가 없으면 `404`가 아니라 빈 배열을 반환한다.

```json
[]
```

### 오류 응답

| 상태 | message | 조건 |
| --- | --- | --- |
| `400` | `INVALID_REFLECTION_DATE` | `before` 누락 또는 날짜 형식 오류 |
| `401` | 인증 오류 | 로그인되지 않은 사용자 |

## 2. 회고 수정

회고 내용을 수정하고 사과 15개를 차감한다. 오늘 작성한 회고는 수정으로 새롭게 보상 조건을 충족한 항목에 한해 보상을 한 번 지급할 수 있다.

### 요청

```http
PATCH /api/v1/reflections/a9fa4138-9ab3-4aba-ae4c-6cce90aa4f47/
Content-Type: application/json
```

```json
{
  "good_points": "오늘 계획했던 일을 차근차근 모두 마무리했어요.",
  "improvement_points": "중간에 휴식 시간을 충분히 챙기지 못했어요."
}
```

| Body | 타입 | 필수 | 제약 |
| --- | --- | --- | --- |
| `good_points` | string | O | 공백 제거 후 1~400자 |
| `improvement_points` | string | O | 공백 제거 후 1~400자 |

`reflection_date`, `created_at`, `updated_at`은 수정할 수 없다.

### 보상 및 차감 규칙

- 수정 전 사과 잔액이 15개 이상이어야 한다.
- 수정 비용은 항상 사과 15개다.
- 오늘 회고만 새 보상을 받을 수 있다.
- 각 항목이 30자 이상을 처음 충족하면 항목당 사과 2개를 지급한다.
- 이미 보상받은 항목은 다시 지급하지 않는다.
- 과거 회고 수정은 글자 수를 새로 충족해도 보상을 지급하지 않는다.
- `token_delta = new_reward - update_cost`다.

| 새 보상 | 비용 | `token_delta` |
| ---: | ---: | ---: |
| 0 | 15 | -15 |
| 2 | 15 | -13 |
| 4 | 15 | -11 |

### 성공 응답

`200 OK`

```json
{
  "reflection_id": "a9fa4138-9ab3-4aba-ae4c-6cce90aa4f47",
  "reflection_date": "2026-06-22",
  "good_points": "오늘 계획했던 일을 차근차근 모두 마무리했어요.",
  "improvement_points": "중간에 휴식 시간을 충분히 챙기지 못했어요.",
  "reward": -11,
  "update_cost": 15,
  "new_reward": 4,
  "token_delta": -11,
  "updated_at": "2026-06-22T12:30:00Z"
}
```

`reward`는 기존 클라이언트 호환을 위해 유지하며 `token_delta`와 같은 값이다.

### 오류 응답

| 상태 | message | 조건 |
| --- | --- | --- |
| `400` | `FIELD_NOT_ALLOWED` | 수정 불가 필드 포함 |
| `401` | 인증 오류 | 로그인되지 않은 사용자 |
| `402` | `INSUFFICIENT_TOKEN_BALANCE` | 수정 전 사과 잔액이 15개 미만 |
| `404` | `REFLECTION_NOT_FOUND` | 회고가 없거나 다른 사용자의 회고 |
| `422` | `INVALID_REFLECTION_CONTENT` | 필수 내용 누락 또는 400자 초과 |

## 3. TODO 완료 및 보상

TODO와 연결된 진행 중 퀘스트를 완료하고, 일일 한도 안에서 사과를 지급한다.

### 요청

```http
PATCH /api/v1/todos/0cebc116-ab83-4d19-8aea-c775e81cb9f5/complete/
```

요청 body는 없다.

### 보상 규칙

- TODO 완료 1건당 사과 1개를 지급한다.
- TODO 완료 보상은 사용자별 하루 최대 10회다.
- 이미 10회 지급받은 날에는 TODO는 완료되지만 `reward`는 `0`이다.
- 보상 지급과 잔액 변경은 `todo_reward` 거래 내역으로 기록한다.

### 성공 응답

`200 OK`

```json
{
  "todo_id": "0cebc116-ab83-4d19-8aea-c775e81cb9f5",
  "status": "COMPLETED",
  "reward": 1,
  "token_balance": 16
}
```

일일 한도에 도달한 경우:

```json
{
  "todo_id": "0cebc116-ab83-4d19-8aea-c775e81cb9f5",
  "status": "COMPLETED",
  "reward": 0,
  "token_balance": 15
}
```

### 함께 발생하는 동작

- 연결된 진행 중 퀘스트를 `COMPLETED`로 변경한다.
- 연결된 퀘스트의 피드 생성을 예약한다.
- 해당 날짜의 모든 TODO가 완료되면 회고 알림을 한 번 생성한다.

### 오류 응답

| 상태 | 응답/조건 |
| --- | --- |
| `401` | 로그인되지 않은 사용자 |
| `404` | TODO가 없거나 다른 사용자의 TODO |
| `409` | `{ "error": "완료할 수 없는 상태입니다." }` |

## 4. 알림 목록 조회

사용자의 알림을 최신순으로 반환한다. 읽은 알림도 응답에 포함되므로 클라이언트가 `is_read`를 기준으로 표시 여부를 결정한다.

### 요청

```http
GET /api/v1/notifications/
```

### 성공 응답

`200 OK`

```json
[
  {
    "notification_id": 42,
    "type": "reflection",
    "title": "오늘도 고생 많았어요",
    "content": "오늘 하루를 같이 정리 해볼까요?",
    "is_read": false,
    "data": {
      "target": "reflection",
      "reflection_date": "2026-06-22"
    },
    "created_at": "2026-06-22T12:30:00Z"
  }
]
```

### 회고 알림 생성 조건

- 해당 날짜의 마지막 미완료 TODO를 완료했을 때 생성한다.
- 자정 배치가 전날 미완료 TODO를 `FAILED`로 변경한 뒤 생성할 수 있다.
- 해당 날짜의 회고를 이미 작성했으면 생성하지 않는다.
- 같은 사용자와 회고 날짜에 대해 이미 알림이 있으면 중복 생성하지 않는다.
- 알림의 `data.reflection_date`는 클릭 시 열 회고 날짜로 사용한다.

## 5. 알림 읽음 처리

### 요청

```http
PATCH /api/v1/notifications/42/read/
```

요청 body는 없다. 이미 읽은 알림에 다시 요청해도 성공한다.

### 성공 응답

`200 OK`

```json
{
  "notification_id": 42,
  "type": "reflection",
  "title": "오늘도 고생 많았어요",
  "content": "오늘 하루를 같이 정리 해볼까요?",
  "is_read": true,
  "data": {
    "target": "reflection",
    "reflection_date": "2026-06-22"
  },
  "created_at": "2026-06-22T12:30:00Z"
}
```

### 오류 응답

| 상태 | 조건 |
| --- | --- |
| `401` | 로그인되지 않은 사용자 |
| `404` | 알림이 없거나 다른 사용자의 알림 |

## 클라이언트 마이그레이션 확인사항

| API | 기존 응답 | 변경 후 확인사항 |
| --- | --- | --- |
| TODO 완료 | `todo_id`, `status` | `reward`, `token_balance` 사용 |
| 회고 수정 | `reward` | `update_cost`, `new_reward`, `token_delta` 사용. `reward`는 호환용 유지 |
| 회고 내역 | 날짜별 반복 조회 | `before` 목록 API 한 번 호출 |
| 알림 | 세션 로컬 알림 | 서버 목록 동기화 및 읽음 API 호출 |

