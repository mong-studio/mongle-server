# 몽글마을 API 명세서 — 회원관리 (AUTH)

> Claude Code 작업 지시용 문서입니다.
> 아래 공통 규칙과 DB 스키마를 반드시 참고하여 구현하세요.

---

## 1. 공통 규칙

### Web API 공통 Headers

| Key | Value | 필수 | 설명 |
|-----|-------|------|------|
| Authorization | `Bearer {access_token}` | 인증 API 제외 필수 | JWT access token |
| Content-Type | `application/json` | 대부분 필수 | 파일 업로드는 `multipart/form-data` |
| Idempotency-Key | UUID string | 생성/결제성 API 권장 | 중복 요청 방지 |
| X-Client-Type | `react` / `godot` | 권장 | 클라이언트 구분 |
| X-Client-Version | `1.0.0` | 권장 | 장애 추적 및 호환성 관리 |

### 공통 성공 응답

단건 응답은 리소스 직접 반환:
```json
{
  "user_id": "uuid",
  "email": "user@example.com"
}
```

목록 응답은 cursor pagination 사용:
```json
{
  "items": [],
  "page": {
    "limit": 20,
    "next_cursor": "eyJpZCI6...",
    "has_next": true
  }
}
```

### 공통 에러 응답
```json
{
  "error": {
    "code": 400,
    "message": "VALIDATION_ERROR",
    "details": {
      "email": ["올바른 이메일 형식이 아닙니다."]
    }
  }
}
```

### DB/Session 기본 정책
- DB 쓰기는 Django에서 `transaction.atomic`으로 묶는다
- TODO 완료처럼 퀘스트 완료, 토큰 지급, 피드 생성이 이어지는 API는 이벤트 로그성 테이블 또는 outbox 패턴을 사용한다

### AI 내부 API 공통 Headers

| Key | Value | 필수 |
|-----|-------|------|
| X-Internal-Service-Token | `internal_service_token` | ✅ |
| Content-Type | `application/json` | ✅ |
| X-Request-Id | UUID string | ✅ |

- 내부 API timeout: 60초 기본, 이미지 생성은 비동기 job 처리
- 모든 내부 API는 `X-Internal-Service-Token` 검증
- `X-Request-Id`를 로그/추적 ID로 사용
- FastAPI는 결과만 반환, 저장은 Django

---

## 2. DB 스키마 (관련 테이블)

### users
| 컬럼 | 타입 | 설명 |
|------|------|------|
| user_id | varchar(36) PK | UUID |
| email | varchar(255) | unique |
| password | varchar(255) | bcrypt 해시 |
| user_name | varchar(8) | |
| job | varchar(20) | |
| birth | date | |
| token_balance | int | default 5 |
| is_active | tinyint(1) | |
| is_aiconsent | tinyint(1) | |
| terms_agreed_at | DATETIME | |
| privacy_agreed_at | DATETIME | |
| created_at | datetime | |
| updated_at | datetime | |

### social_accounts
| 컬럼 | 타입 | 설명 |
|------|------|------|
| social_account_id | int PK | |
| user_id | varchar(36) FK | users.user_id |
| provider | varchar(20) | kakao 등 |
| provider_id | varchar(255) | unique |
| created_at | datetime | |

### refresh_tokens
| 컬럼 | 타입 | 설명 |
|------|------|------|
| refresh_token_id | int PK | |
| user_id | varchar(36) FK | |
| token_hash | varchar(255) | |
| device_info | varchar(255) | |
| expires_at | datetime | |
| created_at | datetime | |

### email_verification_codes
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INT PK | |
| email | varchar(255) | |
| code | varchar(6) | |
| type | varchar(20) | SIGNUP / PASSWORD_RESET |
| is_used | TINYINT(1) | |
| expires_at | DATETIME | |
| created_at | DATETIME | |

---

## 3. API 목록

| ID | Method | Endpoint | 설명 |
|----|--------|----------|------|
| AUTH-001 | POST | `/auth/email-verification` | 이메일 인증 코드 발송 |
| AUTH-002 | POST | `/auth/email-verification/confirm` | 이메일 인증 확인 |
| AUTH-003 | POST | `/auth/signup` | 회원가입 |
| AUTH-004 | POST | `/auth/login` | 로그인 |
| AUTH-005 | POST | `/auth/token/refresh` | 토큰 재발급 |
| AUTH-006 | POST | `/auth/kakao` | 카카오 로그인 URL 생성 |
| AUTH-006-CB | POST | `/auth/kakao/callback` | 카카오 콜백 처리 |
| AUTH-007 | GET | `/users/me` | 내 정보 조회 |
| AUTH-008 | PATCH | `/users/me` | 내 정보 수정 |
| AUTH-009 | PATCH | `/users/me/password` | 비밀번호 변경 |
| AUTH-010 | POST | `/auth/email-verifications` | 비밀번호 찾기 인증 |
| AUTH-011 | POST | `/auth/password/reset` | 비밀번호 찾기 완료 |
| AUTH-012 | POST | `/auth/logout` | 로그아웃 |
| AUTH-013 | DELETE | `/users/me` | 회원 탈퇴 |

---

## 4. API 상세

---

### AUTH-001 이메일 인증 코드 발송
- **Method:** POST
- **Endpoint:** `/auth/email-verification`
- **요구사항:** REQ-AUTH-001

**Request Body**
```json
{
  "email": "user@example.com",
  "purpose": "SIGNUP"
}
```

| 필드 | 타입 | 필수 | 제약조건 |
|------|------|------|----------|
| email | string | ✅ | 소문자 저장, RFC 5321 기준 |
| purpose | enum | ✅ | SIGNUP, PASSWORD_RESET |

**Response 201 Created**
```json
{
  "expires_in_seconds": 180,
  "resend_available_in_seconds": 30
}
```

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 400 | `VALIDATION_ERROR` | 이메일 형식 오류 |
| 409 | `EMAIL_DUPLICATED` | 이미 가입된 이메일 |
| 429 | `EMAIL_VERIFICATION_RATE_LIMITED` | 30초 이내 재발송 |

**비즈니스 로직**
1. purpose가 `SIGNUP`일 시 `users.email` 중복 확인
2. 현재 세션의 같은 purpose 기존 인증 상태 무효화
3. 6자리 영문 대문자 코드 생성
4. 세션 저장: `email_verification = { email, purpose, code_hash, expires_at, resend_available_at, attempts: 0, verified_until: null }`
5. 이메일 발송

---

### AUTH-002 이메일 인증 확인
- **Method:** POST
- **Endpoint:** `/auth/email-verification/confirm`
- **요구사항:** REQ-AUTH-001, REQ-AUTH-007

**Request Body**
```json
{
  "email": "user@example.com",
  "purpose": "SIGNUP",
  "code": "ABCDEF"
}
```

| 필드 | 타입 | 필수 | 제약조건 |
|------|------|------|----------|
| email | string | ✅ | 소문자 저장, RFC 5321 기준 |
| purpose | string | ✅ | SIGNUP, PASSWORD_RESET |
| code | string | ✅ | 랜덤 생성 6자리 대문자 |

**Response 200 OK**
```json
{
  "email": "user@example.com",
  "purpose": "signup",
  "verified": true,
  "verified_until": "2026-06-01T12:30:00Z"
}
```

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 400 | `INVALID_VERFICATION_CODE` | 코드 불일치 |
| 400 | `VERIFICATION_CODE_EXPIRED` | 코드 만료 |
| 429 | `VERIFICATION_ATTEMPT_LIMITED` | 시도 횟수 초과 |

**비즈니스 로직**
1. 요청의 세션 쿠키에서 `email_verification` 조회
2. `email`, `purpose`, `code_hash`, `expires_at`, `attempts` 검증
3. 성공 시 같은 세션에 `verified_at`, `verified_until` 저장 후 `code_hash` 즉시 삭제
4. 회원가입/비밀번호 재설정 완료 시 세션의 `email_verification` 값 삭제

---

### AUTH-003 회원가입
- **Method:** POST
- **Endpoint:** `/auth/signup`
- **요구사항:** REQ-AUTH-001

**Request Headers**
| Key | Value | 필수 |
|-----|-------|------|
| Content-Type | application/json | ✅ |
| Cookie | mongle_email_session=… | ✅ |

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "password123!",
  "user_name": "몽글이",
  "job": "사무직",
  "birth": "1999-07-22",
  "is_aiconsent": true
}
```

| 필드 | 타입 | 필수 | 제약조건 |
|------|------|------|----------|
| email | string | ✅ | RFC 5321 기준 |
| password | string | ✅ | 영문/숫자/특수문자 중 2종 이상, 8~16자 |
| user_name | string | ✅ | 한글/영문/숫자 2~8자 |
| job | string | | |
| birth | date | | |
| is_aiconsent | boolean | ✅ | 선택 동의 |

**Response 201 Created**
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "user_name": "몽글이",
  "token_balance": 5
}
```

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 400 | `VALIDATION_ERROR` | 이메일/비밀번호/닉네임 형식 오류 |
| 400 | `EMAIL_NOT_VERIFIED` | 이메일 인증 미완료 |
| 409 | `EMAIL_DUPLICATED` | 이미 가입된 이메일 |

**비즈니스 로직**
1. 입력값 검증 (이메일 형식, 비밀번호 규칙, 닉네임 규칙)
2. 현재 세션의 `email_verification`이 `purpose=SIGNUP`, 동일 email, `verified_until > now()` 확인
3. 이메일 중복 확인
4. 비밀번호 해싱
5. `users` 생성
6. 세션 `email_verification` 삭제

**주의사항**
- 직업 프리셋 결정 여부 미확정

---

### AUTH-004 로그인
- **Method:** POST
- **Endpoint:** `/auth/login`
- **요구사항:** REQ-AUTH-002

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "password123!",
  "remember_me": true
}
```

| 필드 | 타입 | 필수 | 제약조건 |
|------|------|------|----------|
| email | string | ✅ | RFC 5321 |
| password | string | ✅ | 영문/숫자/특수문자 중 2종 이상, 8~16자 |
| remember_me | boolean | ✅ | 자동 로그인 여부, default false |

**Response 200 OK**
```json
{
  "access_token": "jwt",
  "token_type": "bearer",
  "expires_in_seconds": 3600,
  "users": {
    "user_id": "uuid",
    "email": "user@example.com",
    "user_name": "몽글이",
    "has_character": false
  }
}
```

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 400 | `VALIDATION_ERROR` | 입력값 오류 |
| 401 | `INVALID_CREDENTIALS` | 이메일/비밀번호 불일치 |

**비즈니스 로직**
1. 입력값 검증
2. `users.email`로 활성 사용자 조회
3. 비밀번호 해시 검증
4. access token 발급
5. `remember_me=true` 시 refresh token 생성 후 해시만 DB 저장, HttpOnly cookie로 발급

**주의사항**
- refresh token은 `HttpOnly; Secure; SameSite=Lax` cookie로 발급

---

### AUTH-005 토큰 재발급
- **Method:** POST
- **Endpoint:** `/auth/token/refresh`
- **요구사항:** REQ-AUTH-002

**Response 200 OK**
```json
{
  "access_token": "jwt",
  "expires_in_seconds": 3600
}
```

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 401 | `REFRESH_TOKEN_EXPIRED` | refresh token 만료 |
| 401 | `INVALID_REFRESH_TOKEN` | 인증되지 않은 token |

**비즈니스 로직**
1. HttpOnly cookie에서 refresh token 읽기
2. token hash를 `refresh_tokens`에서 조회
3. 사용자 활성 상태 확인
4. 새 access token 발급
5. refresh token rotation 적용 시 기존 토큰 폐기 후 새 refresh cookie 발급

---

### AUTH-006 카카오 로그인 URL 생성
- **Method:** POST
- **Endpoint:** `/auth/kakao`
- **요구사항:** REQ-AUTH-003

**Request Body**
```json
{
  "redirect_uri": "https://app.example.com/oauth/kakao/callback",
  "scope": "account_email, profile_nickname"
}
```

| 필드 | 타입 | 필수 | 제약조건 |
|------|------|------|----------|
| redirect_uri | string | ✅ | Kakao Developers에 등록된 URI와 완전 일치 |
| scope | string | | 추가 동의 필요 시만 사용, 쉼표 구분 |

**Response 200 OK**
```json
{
  "authorization_url": "https://kauth.kakao.com/oauth/authorize?...",
  "state": "opaque-csrf-state",
  "expires_in_seconds": 600
}
```

**비즈니스 로직**
1. `redirect_uri` 허용 목록 및 Kakao Developers 등록 URI 일치 여부 확인
2. 예측 불가한 `state` 생성 후 10분 TTL로 저장
3. 카카오 인가 URL 생성 (`client_id`, `redirect_uri`, `response_type=code`, `state`, `scope`)
4. `authorization_url` 반환

**주의사항**
- 응답에 `Set-Cookie: mongle_oauth_state=...; HttpOnly; Secure; SameSite=Lax; Max-Age=600` 포함

---

### AUTH-006-CB 카카오 콜백 처리
- **Method:** POST
- **Endpoint:** `/auth/kakao/callback`
- **요구사항:** REQ-AUTH-003

**Request Headers**
| Key | Value | 필수 |
|-----|-------|------|
| Cookie | mongle_oauth_state=… | ✅ |
| Content-Type | application/json | ✅ |

**Request Body**
```json
{
  "code": "kakao-authorization-code",
  "state": "opaque-csrf-state",
  "redirect_uri": "https://app.example.com/oauth/kakao/callback",
  "remember_me": true
}
```

| 필드 | 타입 | 필수 | 제약조건 |
|------|------|------|----------|
| code | string | ✅ | 카카오 인가 코드, 1회성 |
| state | string | ✅ | 로그인 URL 생성 시 발급한 값과 일치 |
| redirect_uri | string | ✅ | 인가 코드 요청에 사용한 URI와 일치 |
| remember_me | boolean | ✅ | true 시 서비스 refresh token cookie 발급 |

**Response 200 OK**
```json
{
  "access_token": "jwt",
  "expires_in_seconds": 3600,
  "is_new": true,
  "user": {
    "user_id": "uuid",
    "email": "user@example.com",
    "user_name": null,
    "provider": "kakao",
    "has_character": false
  }
}
```

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 400 | `VALIDATION_ERROR` | `code`, `state`, `redirect_uri` 형식 오류 |
| 400 | `OAUTH_STATE_MISMATCH` | state 불일치 또는 만료 |
| 400 | `KAKAO_AUTH_DENIED` | 사용자 동의 화면 취소 |
| 401 | `KAKAO_TOKEN_EXCHANGE_FAILED` | 카카오 토큰 요청 실패 또는 인가코드 만료 |
| 401 | `KAKAO_TOKEN_INVALID` | 카카오 액세스 토큰 검증 실패 |
| 409 | `EMAIL_ALREADY_LINKED` | 동일 이메일이 다른 로그인 방식에 이미 연결 |
| 422 | `KAKAO_EMAIL_REQUIRED` | 이메일 동의 없거나 유효/인증된 이메일 없음 |
| 502 | `KAKAO_API_UNAVAILABLE` | 카카오 API 장애 또는 통신 실패 |

**주의사항**
- 최초 소셜 로그인 시 온보딩 필요 (`is_new: true` 응답으로 프론트에서 분기)

---

### AUTH-007 내 정보 조회
- **Method:** GET
- **Endpoint:** `/users/me`

**Response 200 OK**
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "user_name": "몽글이",
  "job": "사무직",
  "birth": "1999-07-22",
  "provider": "EMAIL",
  "created_at": "2026-06-01T12:00:00Z"
}
```

**비즈니스 로직**
1. access token의 사용자 ID로 활성 사용자 조회
2. 개인정보 최소 필드 응답

---

### AUTH-008 내 정보 수정
- **Method:** PATCH
- **Endpoint:** `/users/me`

**Request Body**
```json
{
  "user_name": "망글",
  "job": "무직",
  "birth": "1999-07-22",
  "is_aiconsent": true
}
```

**Response 200 OK**
```json
{
  "email": "user@example.com",
  "user_name": "망글",
  "job": "무직",
  "birth": "1999-07-22",
  "is_aiconsent": true,
  "provider": "email",
  "updated_at": "2026-06-01T12:10:00Z"
}
```

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 400 | `VALIDATION_ERROR` | 닉네임 형식 오류 |

**비즈니스 로직**
1. access token의 사용자 ID로 본인 계정 조회
2. 입력 형식 검증
3. 허용된 필드만 부분 업데이트
4. 수정된 사용자 프로필 반환

---

### AUTH-009 비밀번호 변경
- **Method:** PATCH
- **Endpoint:** `/users/me/password`

**Request Body**
```json
{
  "current_password": "password123!",
  "new_password": "newpass123!"
}
```

**Response 204 No Content**

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 400 | `VALIDATION_ERROR` | 새 비밀번호 형식 오류 |
| 401 | `INVALID_CREDENTIALS` | 현재 비밀번호 불일치 |
| 403 | `PASSWORD_LOGIN_UNAVAILABLE` | 소셜 전용 계정 |

**비즈니스 로직**
1. 이메일 로그인 계정인지 확인
2. 현재 비밀번호 해시 검증
3. 새 비밀번호를 bcrypt로 해싱 후 저장
4. 계정의 기존 refresh token 모두 폐기

**주의사항**
- 비밀번호 변경 시 기존 refresh token 모두 폐기

---

### AUTH-010 비밀번호 찾기 인증
- **Method:** POST
- **Endpoint:** `/auth/email-verifications`

**Request Body**
```json
{
  "email": "user@example.com",
  "purpose": "PASSWORD_RESET"
}
```

**Response 201 Created**
```json
{
  "email": "user@example.com",
  "expires_in_seconds": 180,
  "resend_available_in_seconds": 30
}
```

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 400 | `VALIDATION_ERROR` | 이메일 형식 오류 |
| 403 | `PASSWORD_LOGIN_UNAVAILABLE` | 소셜 로그인 계정 |
| 404 | `USER_NOT_FOUND` | 활성 이메일 로그인 계정 없음 |
| 429 | `EMAIL_VERIFICATION_RATE_LIMITED` | 30초 이내 재발송 |

**비즈니스 로직**
1. 해당 이메일의 활성 이메일 로그인 계정 조회
2. 소셜 전용 계정 시 비밀번호 찾기 차단
3. 현재 세션의 `purpose=PASSWORD_RESET` 기존 인증 상태 무효화
4. 6자리 영어 대문자 인증코드 생성
5. 세션 저장: `email_verification = { email, purpose: "password_reset", code_hash, expires_at, resend_available_at, attempts: 0, verified_until: null }`
6. 이메일 인증 코드 발송

---

### AUTH-011 비밀번호 찾기 완료
- **Method:** POST
- **Endpoint:** `/auth/password/reset`

**Request Headers**
| Key | Value | 필수 |
|-----|-------|------|
| Cookie | mongle_email_session=… | ✅ |
| Content-Type | application/json | ✅ |

**Request Body**
```json
{
  "email": "user@example.com",
  "new_password": "newpass123!"
}
```

**Response 204 No Content**

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 400 | `VALIDATION_ERROR` | 이메일/새 비밀번호 형식 오류 |
| 400 | `EMAIL_NOT_VERIFIED` | 이메일 인증 미완료 |
| 403 | `PASSWORD_LOGIN_UNAVAILABLE` | 소셜 로그인 계정 |
| 404 | `USER_NOT_FOUND` | 활성 이메일 로그인 계정 없음 |

**비즈니스 로직**
1. 세션의 이메일 인증 완료 상태 확인
2. 이메일 로그인 계정인지 확인
3. 활성 계정 여부 확인
4. 새 비밀번호 bcrypt 해싱 후 저장
5. 해당 사용자의 refresh token 모두 폐기
6. 세션의 `email_verification` 값 삭제

---

### AUTH-012 로그아웃
- **Method:** POST
- **Endpoint:** `/auth/logout`

**Response 204 No Content**

**비즈니스 로직**
1. refresh cookie가 있으면 해당 token hash 조회
2. 현재 refresh token만 폐기
3. refresh cookie 만료

---

### AUTH-013 회원 탈퇴
- **Method:** DELETE
- **Endpoint:** `/users/me`

**Response 204 No Content**

**에러**
| 상태코드 | 에러코드 | 상황 |
|----------|----------|------|
| 403 | `USER_DISABLED` | 이미 탈퇴된 계정 |

**비즈니스 로직**
1. `users.status = deleted`
2. 개인 정보 익명화
3. refresh token 폐기
4. 데이터 soft delete

---

## 5. 프로젝트 폴더 구조 참고

```
mongle-server/
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   ├── production.py
│   │   └── test.py
│   └── urls.py
├── apps/
│   └── users/          ← 회원관리 앱 생성 필요
│       ├── models.py
│       ├── views.py
│       ├── urls.py
│       └── serializers.py
├── common/
├── infrastructure/
│   └── email/          ← 이메일 발송 서비스
└── tests/
```

**구현 시 주의사항**
- 앱 생성 후 `config/settings/base.py`의 `INSTALLED_APPS`에 반드시 등록
- 세션 기반 이메일 인증은 Django session framework 활용
- JWT는 djangorestframework-simplejwt 사용