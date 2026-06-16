# 로컬에서 Docker로 실행하기 (초보자용)

이 문서는 **Docker만으로** mongle-server를 처음부터 끝까지 띄우는 방법을 설명합니다.
Python이나 MySQL을 컴퓨터에 직접 설치하지 않아도 됩니다. Docker가 알아서 다 만들어 줍니다.

> 핵심 한 줄: **컨테이너를 띄운 뒤, 컨테이너 안에서 `migrate`와 `seed_dev`를 꼭 실행해야**
> 주민 목록에 캐릭터가 보이고 피드에 데이터가 채워집니다. 이 단계를 빼먹으면 화면이 텅 비어 보입니다.

---

## 0. 무엇이 만들어지나요?

`make docker-up` 한 번이면 아래 4개의 컨테이너가 함께 켜집니다.

| 컨테이너 | 역할 | 포트 |
| --- | --- | --- |
| `web` | Django 서버 (API) | http://localhost:8000 |
| `db` | MySQL 데이터베이스 | 3306 |
| `redis` | 캐시 / 작업 큐 | 6379 |
| `worker` | Celery 백그라운드 작업 | (포트 없음) |

여기서 중요한 점: **`db` 컨테이너는 완전히 새 빈 데이터베이스입니다.**
내 컴퓨터에 따로 깔린 MySQL이나 다른 팀원의 DB와 아무 상관이 없습니다.
그래서 처음에는 사용자도, 캐릭터도, 피드도 하나도 없습니다. 우리가 직접 채워 넣어야 합니다.

---

## 1. 준비물

- **Docker Desktop** 설치 후 실행해 둡니다. (메뉴 막대/작업 표시줄에 고래 아이콘이 떠 있어야 합니다.)
  - 확인: 터미널에서 `docker --version` 입력 시 버전이 나오면 OK.

---

## 2. 환경 변수 파일 만들기

프로젝트 루트(`mongle-server/`)에서 한 번만 실행합니다.

```bash
cp .env.example .env
```

`.env.example`의 기본값은 **Docker용으로 이미 맞춰져 있습니다.** 처음에는 그대로 둬도 됩니다.

> 주의할 점 하나: `.env` 안의 `MYSQL_PASSWORD`와 `DATABASE_URL`에 적힌 비밀번호는 **반드시 같아야** 합니다.
> 기본값은 둘 다 `mongle_password`라서 손대지 않으면 문제없습니다.

---

## 3. 컨테이너 띄우기

```bash
make docker-up
```

- 내부적으로 `docker compose up --build`를 실행합니다.
- 처음에는 이미지를 빌드하느라 몇 분 걸릴 수 있습니다.
- 이 명령은 **터미널을 계속 차지합니다(로그가 흐릅니다).** 끄지 말고 그대로 두세요.

`web` 로그에 아래 비슷한 줄이 보이면 서버가 뜬 것입니다.

```
Starting development server at http://0.0.0.0:8000/
```

---

## 4. (중요) DB 구조 만들기 + 시드 데이터 넣기

3번에서 띄운 터미널은 로그가 흐르고 있으므로, **새 터미널 탭/창을 하나 더 열어** 같은
`mongle-server/` 폴더에서 아래를 실행합니다.

```bash
# (1) 데이터베이스 테이블을 만든다
docker compose exec -T web python manage.py migrate

# (2) 기본 계정 + 캐릭터 + 퀘스트 + 피드 데이터를 넣는다
docker compose exec -T web python manage.py seed_dev
```

`docker compose exec -T web ...`는 "이미 떠 있는 `web` 컨테이너 **안에서** 명령을 실행"한다는 뜻입니다.
내 컴퓨터가 아니라 컨테이너 안의 DB에 데이터가 들어가야 하므로 이 방식이 중요합니다.

> `-T`는 TTY 할당을 끄는 옵션입니다. `migrate`·`seed_dev`처럼 입력 없이 한 번 실행하는
> 명령은 스크립트/CI 등 TTY가 없는 환경에서도 안전하게 돌도록 `-T`를 붙입니다.
> (일반 터미널에서 손으로 칠 때는 없어도 동작합니다.) 반대로 대화형으로 들어가는
> `manage.py shell` 같은 명령은 `-T` 없이 실행해야 합니다.

`seed_dev`가 성공하면 아래처럼 출력됩니다.

```
시드 데이터 생성 완료
  슈퍼유저: admin@mongle.dev / mongle1234!
  데모유저: demo@mongle.dev / mongle1234!
```

이때 만들어지는 데이터(계정마다):

- 기본 태그 5개, 오늘 할 일 3개, 일정 1개, 회고 1개
- **캐릭터 "몽글" 1개** (주황 여우 이미지)
- **퀘스트 3개**, **피드(post) 3개**

> 💡 `seed_dev`는 **여러 번 실행해도 안전**합니다(멱등). 데이터가 중복으로 쌓이지 않고,
> 잘못된 권한 같은 것이 있으면 다시 돌릴 때 바로잡아 줍니다.

---

## 5. 잘 됐는지 확인하기

1. **서버 상태 확인**

   ```bash
   curl http://localhost:8000/health/
   ```

   결과가 `{"status": "ok"}`면 정상입니다.

2. **캐릭터 이미지 확인** — 브라우저에서 아래 주소를 열어 그림이 보이면 OK.
   유저별로 이미지가 다릅니다(demo=여우, admin=토끼).

   ```
   http://localhost:8000/static/seed/demo-character.png
   http://localhost:8000/static/seed/admin-character.png
   ```

3. **로그인** — 프론트엔드(웹)에서 아래 계정으로 로그인합니다.

   | 용도 | 이메일 | 비밀번호 |
   | --- | --- | --- |
   | 관리자 | `admin@mongle.dev` | `mongle1234!` |
   | 데모(일반 사용자) | `demo@mongle.dev` | `mongle1234!` |

   로그인 후 주민 목록에 "몽글" 캐릭터가 보이고, 피드에 글 3개가 보이면 성공입니다.

---

## 6. 이미 띄워둔 팀원이라면 (기존 환경 업데이트)

전에 이미 Docker로 띄워서 쓰고 있었다면 **DB를 지울 필요가 없습니다.** 최신 코드를 받고
시드만 다시 돌리면 됩니다. `seed_dev`는 멱등이라 기존 데이터를 망가뜨리지 않습니다.

```bash
# 1) 최신 코드 받기 (변경된 시드 코드 + 캐릭터 이미지 파일이 함께 들어옵니다)
git pull

# 2) 컨테이너가 꺼져 있으면 다시 띄우기
make docker-up

# 3) (안전하게) 마이그레이션 + 시드 다시 실행 — 새 터미널에서
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py seed_dev
```

다시 돌리면 기존 환경에서도 아래가 자동으로 정리됩니다.

- 데모 계정에 잘못 부여됐던 **admin 권한이 회수**됩니다.
- 캐릭터 이미지가 **유저별 시드 이미지로 갱신**됩니다(demo=여우, admin=토끼).
- 그동안 없던 **퀘스트·피드 데이터가 새로 채워집니다.**

> 이미지가 여전히 안 보이면, `git pull`로 `static/seed/demo-character.png` ·
> `static/seed/admin-character.png` 파일이 잘 받아졌는지 확인하세요.
> 컨테이너는 코드 폴더를 그대로 공유(volume)하므로 이미지 파일만 있으면 재빌드 없이 바로 보입니다.

---

## 7. 자주 겪는 문제 (Troubleshooting)

### ❗ 주민 목록에 캐릭터가 안 보이거나 피드가 텅 비어 있어요

가장 흔한 원인은 **4번(시드) 단계를 안 했거나, 컨테이너 밖에서 잘못 실행한 경우**입니다.
컨테이너 안에서 다시 실행하세요.

```bash
docker compose exec -T web python manage.py seed_dev
```

> 다른 팀원 화면에서 데이터가 안 보이는 것도 같은 이유입니다. 각자 자기 Docker DB에
> `seed_dev`를 돌려야 자기 화면에 데이터가 채워집니다. DB는 사람마다 따로입니다.

### ❗ "Port is already allocated" / 포트 충돌 (8000 또는 3306)

이미 다른 프로그램이 그 포트를 쓰고 있습니다. 보통 로컬에 따로 켜둔 MySQL(3306)이나
다른 개발 서버(8000)입니다. 그 프로그램을 끄고 다시 `make docker-up` 하세요.

### ❗ DB 비밀번호 관련 에러 (Access denied)

`.env`의 `MYSQL_PASSWORD`와 `DATABASE_URL`의 비밀번호가 서로 다르면 납니다. 둘을 같게 맞추고,
이미 잘못된 비밀번호로 DB가 만들어졌다면 아래 8번으로 **완전 초기화** 후 다시 띄우세요.

### ❗ 모델/코드를 바꿨는데 반영이 안 돼요

- 모델(DB 구조)을 바꿨다면 마이그레이션을 다시 만들고 적용합니다.

  ```bash
  docker compose exec -T web python manage.py makemigrations
  docker compose exec -T web python manage.py migrate
  ```

- 의존성(`pyproject.toml`)을 바꿨다면 이미지를 다시 빌드해야 합니다: `make docker-down` 후 `make docker-up`.

### ❗ 캐릭터를 더 못 만들어요 (생성 한도 / 하루 생성 한도 초과)

두 가지 한도가 있습니다 — **활성 캐릭터 최대 10개**, **하루 생성 최대 3회**.
하루 한도는 생성 로그(`ImgGenLog`)로 세는데, **생성이 실패해도 로그가 쌓여 한도를 소모**합니다
(AI 서비스 미연결로 실패가 반복되면 금방 3회를 다 씁니다).

개발용 초기화 명령으로 둘 다 한 번에 풉니다:

```bash
# 시드(몽글)는 남기고 나머지 캐릭터 비활성화 + 오늘 생성 로그 삭제
docker compose exec -T web python manage.py reset_limits --email demo@mongle.dev --keep-seed

# 그 계정 캐릭터를 전부 비활성화하려면 --keep-seed 를 뺀다
docker compose exec -T web python manage.py reset_limits --email demo@mongle.dev
```

캐릭터는 soft-delete(`is_active=False`)라 행은 남고 한도/주민 목록에서만 빠집니다.

---

## 8. 멈추기 / 완전 초기화

```bash
# 컨테이너 멈추기 (데이터는 유지됨)
make docker-down

# 데이터까지 싹 지우고 처음부터 다시 시작하고 싶을 때 (DB 볼륨 삭제)
docker compose down -v
```

`docker compose down -v`로 DB를 비운 뒤에는 **4번(migrate + seed_dev)을 다시 실행해야** 합니다.

---

## 9. 명령어 치트시트 (Docker)

| 명령어 | 무엇을 하나요? |
| --- | --- |
| `make docker-up` | 컨테이너 전체(web/db/redis/worker)를 빌드 후 실행 |
| `make docker-down` | 컨테이너를 멈춤 (데이터는 유지) |
| `make docker-logs` | `web` 컨테이너 로그를 계속 보기 |
| `docker compose exec -T web python manage.py migrate` | 컨테이너 안에서 DB 테이블 생성/갱신 |
| `docker compose exec -T web python manage.py seed_dev` | 컨테이너 안에서 기본 계정·캐릭터·피드 시드 |
| `docker compose exec -T web python manage.py reset_limits --email <이메일> [--keep-seed]` | 캐릭터/하루 생성 한도 초기화 |
| `docker compose exec web python manage.py shell` | 컨테이너 안에서 Django shell 열기 |
| `docker compose down -v` | DB 볼륨까지 삭제 (완전 초기화) |

---

## 10. (선택) 시드 캐릭터 이미지를 S3에 올려서 쓰기

기본값은 dev 서버가 서빙하는 **로컬 static 이미지**(`/static/seed/...`)입니다. 로컬 개발만
한다면 이걸로 충분합니다. 배포 환경처럼 **S3/CloudFront에 올린 이미지를 쓰고 싶을 때만**
아래를 따라 하세요.

### 키 규칙 — 실제 유저 업로드와 안 섞이게

실제 캐릭터 생성 이미지는 유저별로 `mongle-village/source-images/<user_id>/...` 아래에
쌓입니다. 시드 유저의 `user_id`는 환경마다 랜덤이라 미리 그 경로를 만들 수 없으므로,
시드 이미지는 **`mongle-village/seed/` 아래에 역할로 식별되는 고정 이름**으로 둡니다.
이러면 S3만 봐도 "이건 시드/데모 자산"임이 드러나고 실제 유저 데이터와 경로가 겹치지 않습니다.

```
mongle-village/seed/demo-character.png    ← demo 유저 캐릭터(여우)
mongle-village/seed/admin-character.png   ← admin 유저 캐릭터(토끼)
```

### 1) S3에 업로드

```bash
aws s3 cp static/seed/demo-character.png \
  s3://<your-bucket>/mongle-village/seed/demo-character.png --content-type image/png
aws s3 cp static/seed/admin-character.png \
  s3://<your-bucket>/mongle-village/seed/admin-character.png --content-type image/png
```

> 시드 이미지는 만료되는 presigned URL이 아니라 **항상 떠 있어야** 하므로, 해당 객체를
> 공개 읽기로 두거나(버킷 정책/ACL) CloudFront로 서빙해야 브라우저에서 바로 보입니다.

### 2) `.env`에 URL 지정 (유저별)

```bash
SEED_DEMO_IMAGE_URL=https://<your-bucket>.s3.ap-northeast-2.amazonaws.com/mongle-village/seed/demo-character.png
SEED_ADMIN_IMAGE_URL=https://<your-bucket>.s3.ap-northeast-2.amazonaws.com/mongle-village/seed/admin-character.png
# CloudFront가 있다면 그 배포 URL을 써도 됩니다.
```

비워두면 로컬 static(`http://localhost:8000/static/seed/<파일명>`)으로 자동 fallback됩니다.

### 3) 재시드

```bash
docker compose exec -T web python manage.py seed_dev
```

재시드하면 기존 캐릭터·피드 이미지(예: 옛 `example.com` placeholder)도 지정한 S3 URL로
갱신됩니다.

---

Python을 직접 설치해서 `.venv`로 실행하는 방법은 [setup-guide.md](setup-guide.md)를 참고하세요.
