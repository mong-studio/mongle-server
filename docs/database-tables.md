# Database Tables

mongle-server의 전체 DB 테이블 구성 및 용도 정리.

총 18개 테이블 / 5개 Django 앱

---

## 목차

- [Users 앱](#users-앱)
  - [users](#users)
  - [social_accounts](#social_accounts)
  - [refresh_tokens](#refresh_tokens)
  - [token_transactions](#token_transactions)
  - [notifications](#notifications)
- [Todos 앱](#todos-앱)
  - [tags](#tags)
  - [todos](#todos)
  - [schedules](#schedules)
  - [reflections](#reflections)
- [Characters 앱](#characters-앱)
  - [source_images](#source_images)
  - [character_generation_jobs](#character_generation_jobs)
  - [characters](#characters)
  - [character_homes](#character_homes)
  - [img_gen_logs](#img_gen_logs)
- [Quests 앱](#quests-앱)
  - [quests](#quests)
- [Posts 앱](#posts-앱)
  - [posts](#posts)
  - [comments](#comments)
  - [replies](#replies)

---

## Users 앱

### users

회원 계정 정보. AbstractBaseUser 기반 커스텀 유저 모델.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| user_id | UUID (PK) | 유저 고유 식별자 |
| email | EmailField (unique) | 로그인 ID |
| user_name | CharField(8) | 닉네임 |
| job | CharField(20) | 직업 (선택) |
| birth | DateField | 생년월일 (필수) |
| token_balance | IntegerField | 보유 토큰 수 (기본 5) |
| is_active | BooleanField | 활성 여부 |
| is_aiconsent | BooleanField | AI 학습 동의 여부 |
| is_staff | BooleanField | 관리자 여부 |
| login_type | CharField(10) | 가입 방식 (email / kakao / google / naver) |
| created_at | DateTimeField | 가입일시 |
| updated_at | DateTimeField | 수정일시 |

---

### social_accounts

소셜 로그인 연동 정보. 한 유저가 여러 소셜 계정을 연결할 수 있음.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| social_account_id | AutoField (PK) | 식별자 |
| user_id | FK → users | 연결된 유저 |
| provider | CharField(20) | OAuth 제공자 (kakao / google / naver) |
| provider_id | CharField(255, unique) | 제공자 측 유저 ID |
| created_at | DateTimeField | 연결일시 |

---

### refresh_tokens

JWT 리프레시 토큰 저장소. 기기별로 발급·관리.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| refresh_token_id | AutoField (PK) | 식별자 |
| user_id | FK → users | 토큰 소유 유저 |
| token_hash | CharField(255, unique) | 토큰 해시값 |
| device_info | CharField(255) | 발급 기기 정보 |
| expires_at | DateTimeField | 만료일시 |
| persistent | BooleanField | 장기 유지 여부 (로그인 유지 체크) |
| created_at | DateTimeField | 발급일시 |

---

### token_transactions

서비스 내 토큰 사용/획득 내역. 캐릭터 생성, 퀘스트 보상 등 토큰 흐름을 기록.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| token_transaction_id | UUID (PK) | 식별자 |
| user_id | FK → users | 관련 유저 |
| amount | IntegerField | 변동량 (양수: 획득, 음수: 사용) |
| type | CharField(30) | 거래 종류 (예: character_generation, quest_reward) |
| reference_id | CharField(255) | 관련 리소스 ID (job_id, quest_id 등) |
| created_at | DateTimeField | 거래일시 |

---

### notifications

유저에게 전달되는 알림 내역.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| notification_id | AutoField (PK) | 식별자 |
| user_id | FK → users | 수신 유저 |
| type | CharField(20) | 알림 종류 |
| title | CharField(100) | 알림 제목 |
| content | TextField | 알림 내용 |
| is_read | BooleanField | 읽음 여부 |
| created_at | DateTimeField | 생성일시 |
| updated_at | DateTimeField | 수정일시 |

---

## Todos 앱

### tags

유저별 태그. 투두와 일정을 분류하는 데 사용. 같은 유저 내에서 내용이 중복될 수 없음.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| tag_id | IntegerField (PK) | 식별자 |
| user_id | FK → users | 태그 소유 유저 |
| content | CharField(20) | 태그명 |
| color | CharField(7) | 태그 색상 (hex, 예: #E7D39F) |

**제약:** `UNIQUE(user_id, content)` — 동일 유저가 같은 이름의 태그를 중복 생성 불가

---

### todos

유저의 할 일 항목. 날짜별로 관리되며 태그로 분류.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| todo_id | UUID (PK) | 식별자 |
| user_id | FK → users | 작성 유저 |
| tag_id | FK → tags (PROTECT) | 분류 태그 |
| content | CharField(20) | 할 일 내용 |
| status | CharField(20) | 상태 (IN_PROGRESS / COMPLETED / FAILED) |
| todo_date | DateField | 해당 날짜 |
| created_at | DateTimeField | 생성일시 |
| updated_at | DateTimeField | 수정일시 |

**관계:** 태그 삭제 시 PROTECT (태그가 있는 투두가 있으면 태그 삭제 불가)

---

### schedules

유저의 일정. 기간이 있는 이벤트를 태그로 분류하여 관리.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| schedule_id | UUID (PK) | 식별자 |
| user_id | FK → users | 작성 유저 |
| tag_id | FK → tags (PROTECT) | 분류 태그 |
| title | CharField(20) | 일정 제목 |
| description | CharField(200) | 설명 (선택) |
| start_date | DateField | 시작일 |
| end_date | DateField (nullable) | 종료일 (당일 일정이면 null) |

---

### reflections

유저의 날짜별 회고. 하루를 돌아보며 잘한 점과 개선점을 기록.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| reflection_id | UUID (PK) | 식별자 |
| user_id | FK → users | 작성 유저 |
| reflection_date | DateField | 회고 날짜 |
| good_points | TextField (nullable) | 잘한 점 |
| improvement_points | TextField (nullable) | 개선할 점 |
| created_at | DateTimeField | 생성일시 |
| updated_at | DateTimeField | 수정일시 |

---

## Characters 앱

### source_images

AI 캐릭터 생성을 위한 원본 이미지. Presigned URL 방식으로 S3에 직접 업로드.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| source_img_id | UUID (PK) | 식별자 |
| user_id | FK → users | 업로드한 유저 |
| object_key | CharField(500) | S3 오브젝트 키 |
| content_type | CharField(50) | MIME 타입 (예: image/jpeg) |
| status | CharField(20) | 업로드 상태 (PENDING_UPLOAD / UPLOAD_COMPLETED / UPLOAD_EXPIRED) |
| expires_at | DateTimeField | Presigned URL 만료일시 |
| created_at | DateTimeField | 생성일시 |

**흐름:** 서버에서 Presigned URL 발급 → 클라이언트가 S3 직접 업로드 → status를 UPLOAD_COMPLETED로 변경

---

### character_generation_jobs

AI 서버에 요청하는 캐릭터 생성 작업. Celery 비동기 태스크로 처리.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| job_id | UUID (PK) | 식별자 |
| user_id | FK → users | 요청 유저 |
| source_image_id | FK → source_images (SET_NULL, nullable) | 원본 이미지 |
| requested_name | CharField(50) | 요청한 캐릭터 이름 |
| requested_persona | TextField | 요청한 캐릭터 성격 설명 |
| personality_keywords | JSONField | 성격 키워드 목록 |
| custom_prompt | CharField(200) | 추가 커스텀 프롬프트 |
| status | CharField(20) | 작업 상태 (QUEUED / IN_PROGRESS / SUCCEEDED / FAILED / CONSUMED) |
| gen_img_object_key | CharField(500) | 생성된 이미지 S3 키 |
| gen_img_url | CharField(500) | 생성된 이미지 URL |
| persona | TextField | AI가 생성한 최종 페르소나 |
| error_code | CharField(50) | 실패 시 에러 코드 |
| error_message | CharField(255) | 실패 시 에러 메시지 |
| created_at | DateTimeField | 요청일시 |
| updated_at | DateTimeField | 수정일시 |

**흐름:** QUEUED → (Celery 처리) → IN_PROGRESS → SUCCEEDED / FAILED → (캐릭터 저장 후) CONSUMED

---

### characters

유저의 AI 캐릭터. 생성 완료된 잡에서 확정된 캐릭터를 저장.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| character_id | UUID (PK) | 식별자 |
| user_id | FK → users | 소유 유저 |
| generation_job_id | OneToOne → character_generation_jobs (SET_NULL, nullable) | 생성 출처 잡 |
| character_name | CharField(8) | 캐릭터 이름 |
| origin_img_url | TextField | 원본 이미지 URL (presigned URL이 500자 초과 가능) |
| gen_img_url | TextField | AI 생성 이미지 URL |
| persona | TextField | 캐릭터 페르소나 |
| visual | CharField(255) | 외관 설명 (custom_prompt 기반) |
| is_active | BooleanField | 활성 캐릭터 여부 |
| created_at | DateTimeField | 생성일시 |
| updated_at | DateTimeField | 수정일시 |

---

### character_homes

캐릭터의 집. 캐릭터 생성 시 자동으로 랜덤 외관 타입이 배정되어 생성됨.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| house_id | UUID (PK) | 식별자 |
| character_id | OneToOne → characters | 소유 캐릭터 |
| exterior_type | CharField(30) | 집 외관 타입 (house_yellow / house_blue / house_green / house_purple) |
| position_x | IntegerField | 마을 내 X 좌표 (기본 0) |
| position_y | IntegerField | 마을 내 Y 좌표 (기본 0) |
| created_at | DateTimeField | 생성일시 |

**생성 방식:** `post_save` 시그널로 Character 생성 시 자동 생성

---

### img_gen_logs

이미지 생성 횟수 로그. 유저별 AI 이미지 생성 사용량 추적.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| img_gen_log_id | AutoField (PK) | 식별자 |
| user_id | FK → users | 유저 |
| gen_cnt | IntegerField | 생성 횟수 |
| created_at | DateTimeField | 기록일시 |
| updated_at | DateTimeField | 수정일시 |

---

## Quests 앱

### quests

캐릭터가 유저의 투두를 기반으로 제시하는 퀘스트. 캐릭터와 투두를 연결하는 핵심 테이블.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| quest_id | UUID (PK) | 식별자 |
| character_id | FK → characters | 퀘스트를 제시한 캐릭터 |
| todo_id | FK → todos | 연결된 투두 항목 |
| content | TextField | 퀘스트 내용 (캐릭터가 생성) |
| status | CharField(20) | 퀘스트 상태 (IN_PROGRESS / COMPLETED / FAILED) |
| character_reaction | TextField | 완료/실패 시 캐릭터 반응 메시지 |
| created_at | DateTimeField | 생성일시 |
| updated_at | DateTimeField | 수정일시 |

---

## Posts 앱

### posts

퀘스트 완료 후 캐릭터가 작성하는 게시글. 마을 피드에 표시됨.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| post_id | UUID (PK) | 식별자 |
| character_id | FK → characters | 작성한 캐릭터 |
| quest_id | FK → quests | 연결된 퀘스트 |
| content | CharField(150) | 게시글 내용 |
| img_url | CharField(500) | 첨부 이미지 URL |
| is_liked | BooleanField | 좋아요 여부 |
| created_at | DateTimeField | 게시일시 |
| updated_at | DateTimeField | 수정일시 |

---

### comments

유저가 게시글에 다는 댓글.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| comment_id | UUID (PK) | 식별자 |
| post_id | FK → posts | 대상 게시글 |
| user_id | FK → users | 작성 유저 |
| content | CharField(50) | 댓글 내용 |
| created_at | DateTimeField | 작성일시 |

---

### replies

캐릭터가 댓글에 다는 답글. 캐릭터가 유저 댓글에 응답하는 상호작용.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| reply_id | UUID (PK) | 식별자 |
| comment_id | FK → comments | 대상 댓글 |
| character_id | FK → characters | 답글 작성 캐릭터 |
| content | TextField | 답글 내용 |
| created_at | DateTimeField | 작성일시 |

---

## 테이블 관계 요약

```
users
 ├── social_accounts       (1:N) 소셜 로그인 연동
 ├── refresh_tokens        (1:N) JWT 토큰 관리
 ├── token_transactions    (1:N) 토큰 사용/획득 이력
 ├── notifications         (1:N) 알림
 ├── tags                  (1:N) 투두/일정 분류 태그
 │    ├── todos            (1:N) 할 일
 │    └── schedules        (1:N) 일정
 ├── reflections           (1:N) 날짜별 회고
 ├── source_images         (1:N) AI 생성용 원본 이미지
 ├── character_generation_jobs (1:N) 캐릭터 생성 작업
 │    └── characters       (1:1) 생성된 캐릭터
 │         ├── character_homes (1:1) 캐릭터 집 (자동 생성)
 │         ├── quests      (1:N) 퀘스트 (todo 연결)
 │         ├── posts       (1:N) 마을 피드 게시글
 │         └── replies     (1:N) 댓글 답글
 └── img_gen_logs          (1:N) 이미지 생성 횟수 기록

todos
 └── quests                (1:N) 해당 투두에서 파생된 퀘스트

posts
 └── comments              (1:N) 게시글 댓글
      └── replies          (1:N) 댓글에 대한 캐릭터 답글
```
