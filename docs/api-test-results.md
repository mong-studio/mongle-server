# API 테스트 결과

날짜: 2026-06-08

## 테스트 환경

- 서버: `http://localhost:8000`
- 테스트 계정: `test@mongle.com` / `test1234!`
- 툴: Postman

---

## 인증

### 로그인
```
POST /api/v1/auth/login/
```

**Request Body:**
```json
{
  "email": "test@mongle.com",
  "password": "test1234!"
}
```

**Response 200:**
```json
{
  "access": "eyJhbGci...",
  "refresh": "eyJhbGci..."
}
```

---

### 내 정보 조회
```
GET /api/v1/auth/me/
Authorization: Bearer {access_token}
```

**Response 200:**
```json
{
  "user_id": "024ad3e5-a8c4-4512-bc1a-bd7075e52d82",
  "email": "test@mongle.com",
  "user_name": "몽글이",
  "token_balance": 5,
  "created_at": "2026-06-08T17:18:54.729294+09:00"
}
```

---

## 캐릭터 (Characters)

### CHAR-002: AI 생성 Job 등록
```
POST /api/v1/characters/generation-jobs/
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "personality_keywords": ["활발한", "긍정적인"]
}
```

**Response 202:**
```json
{
  "job_id": "0ea394d5-24e6-46bc-bef7-32ccdc4aa3ac",
  "status": "queued",
  "estimated_seconds": 60
}
```

---

### CHAR-003: Job 상태 조회
```
GET /api/v1/characters/generation-jobs/{job_id}/
Authorization: Bearer {access_token}
```

**Response 200:**
```json
{
  "job_id": "0ea394d5-24e6-46bc-bef7-32ccdc4aa3ac",
  "status": "queued",
  "result": null,
  "created_at": "2026-06-08T17:48:37.109804+09:00",
  "updated_at": "2026-06-08T17:48:37.109831+09:00"
}
```

> ⚠️ AI 서버 미연결 시 `queued` 상태에서 진행되지 않음. Celery 워커 실행 필요.

---

### CHAR-004: 캐릭터 등록
```
POST /api/v1/characters/register/
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "gen_job_id": "0ea394d5-24e6-46bc-bef7-32ccdc4aa3ac",
  "name": "몽글이",
  "persona": "활발하고 긍정적인 성격"
}
```

**Response 201:**
```json
{
  "character_id": "9f048098-d249-40b4-bb41-39ac0daa2853",
  "name": "몽글이",
  "gen_img_url": "https://example.com/test-character.png",
  "persona": "활발하고 긍정적인 성격",
  "created_at": "2026-06-08T08:55:06.414603+00:00"
}
```

---

### CHAR-005: 캐릭터 목록 조회
```
GET /api/v1/characters/
Authorization: Bearer {access_token}
```

**Response 200:**
```json
{
  "items": [
    {
      "character_id": "b5a88842-2e18-474f-a887-b3a0ad05faab",
      "character_name": "돌맹이",
      "gen_img_url": "https://example.com/test-character2.png",
      "active_quest_count": 0
    }
  ],
  "page": {
    "limit": 20,
    "next_cursor": null,
    "has_next": false
  }
}
```

---

### CHAR-006: 캐릭터 상세 조회
```
GET /api/v1/characters/{character_id}/
Authorization: Bearer {access_token}
```

**Response 200:**
```json
{
  "character_id": "9f048098-d249-40b4-bb41-39ac0daa2853",
  "character_name": "몽글이",
  "gen_img_url": "https://example.com/test-character.png",
  "persona": "활발하고 긍정적인 성격",
  "active_quests": []
}
```

---

### CHAR-007: 캐릭터 삭제
```
DELETE /api/v1/characters/{character_id}/delete/
Authorization: Bearer {access_token}
```

**Response 204:** (성공 시 본문 없음)

**Response 409:** (마지막 캐릭터 삭제 시도 시)
```json
{
  "error": "LAST_CHARACTER"
}
```

---

## 퀘스트 (Quests)

### QUES-001: 퀘스트 목록 조회
```
GET /api/v1/characters/{character_id}/quests/
Authorization: Bearer {access_token}
```

**Response 200:**
```json
{
  "items": [],
  "page": {
    "limit": 20,
    "next_cursor": null,
    "has_next": false
  }
}
```

---

## 테스트 결과 요약

| 엔드포인트 | 메서드 | 결과 |
|---|---|---|
| `/api/v1/auth/login/` | POST | ✅ |
| `/api/v1/auth/me/` | GET | ✅ |
| `/api/v1/characters/generation-jobs/` | POST | ✅ |
| `/api/v1/characters/generation-jobs/{job_id}/` | GET | ✅ |
| `/api/v1/characters/register/` | POST | ✅ |
| `/api/v1/characters/` | GET | ✅ |
| `/api/v1/characters/{character_id}/` | GET | ✅ |
| `/api/v1/characters/{character_id}/delete/` | DELETE | ✅ |
| `/api/v1/characters/{character_id}/quests/` | GET | ✅ |

## 미테스트 항목

| 엔드포인트 | 이유 |
|---|---|
| `CHAR-001` S3 presigned URL 발급 | AWS 설정 필요 |
| `CHAR-002` AI 생성 실제 동작 | AI 서버 + Celery 워커 필요 |
| 이메일 인증 / 회원가입 | SMTP 설정 필요 |
