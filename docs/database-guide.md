# 데이터베이스 세팅 가이드

> MySQL 9.7.0 + MySQL Workbench 기준 (macOS)
> 처음 세팅하는 사람도 순서대로 따라하면 됩니다.

---

## 순서 요약

1. MySQL 설치
2. MySQL Workbench 설치
3. MySQL PATH 설정
4. DB 및 유저 생성
5. Workbench Connection 생성
6. 테이블 생성 (SQL 실행)
7. `.env` 설정
8. Django 마이그레이션 동기화

---

## 1. MySQL 설치

1. [MySQL 공식 사이트](https://dev.mysql.com/downloads/mysql/)에서 **MySQL Community Server 9.7.0** 다운로드
   - 운영체제: **macOS**
   - CPU: M1/M2/M3 Mac이면 **ARM**, Intel Mac이면 **x86** 선택
2. 다운로드한 `.dmg` 파일 실행 → 설치 진행
3. 설치 중 **root 비밀번호 입력창**이 나옵니다 → 원하는 비밀번호 설정 후 **반드시 기억해두기**
4. 설치 완료 후 Mac **시스템 설정** 열기 → 맨 아래 **MySQL** 항목 클릭 → **초록불** 확인
   - 빨간불이면 **Start MySQL Server** 클릭

---

## 2. MySQL Workbench 설치

1. [MySQL Workbench 다운로드](https://dev.mysql.com/downloads/workbench/)에서 설치
2. 설치 후 Workbench 실행 시 아래 경고가 뜰 수 있습니다:
   > "Incompatible/nonstandard server version 9.7.0 detected"

   → **Continue Anyway** 클릭하면 정상 동작합니다.

---

## 3. MySQL PATH 설정

터미널에서 MySQL 명령어를 짧게 쓸 수 있도록 PATH를 등록합니다.
**한 번만** 하면 됩니다.

터미널을 열고 아래 두 줄을 순서대로 실행:

```bash
echo 'export PATH="/usr/local/mysql/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

확인:

```bash
mysql --version
```

`mysql  Ver 9.7.0 ...` 처럼 버전이 출력되면 완료.

---

## 4. DB 및 유저 생성

터미널에서 아래 명령어 실행. `root비밀번호` 부분을 **1단계에서 설정한 비밀번호**로 교체:

```bash
mysql -u root -proot비밀번호 -e "
CREATE DATABASE IF NOT EXISTS mongle_village CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'mongle'@'localhost' IDENTIFIED BY 'mongle';
GRANT ALL PRIVILEGES ON mongle_village.* TO 'mongle'@'localhost';
FLUSH PRIVILEGES;
"
```

> 예시: root 비밀번호가 `12341234`이면 `-p12341234` 로 입력

생성 확인:

```bash
mysql -u root -proot비밀번호 -e "SHOW DATABASES;"
```

목록에 `mongle_village` 가 보이면 완료.

---

## 5. Workbench Connection 생성

1. Workbench 실행
2. 홈 화면 **MySQL Connections** 옆 **`+`** 버튼 클릭
3. 아래 값 입력:

| 항목 | 입력값 |
|------|--------|
| Connection Name | `mongle_village` |
| Hostname | `127.0.0.1` |
| Port | `3306` |
| Username | `root` |
| Default Schema | `mongle_village` |

4. **Test Connection** 클릭 → root 비밀번호 입력 → "Successfully made the MySQL connection" 메시지 확인
5. **OK** → **Close**
6. 홈 화면에서 `mongle_village` connection 더블클릭하여 접속

---

## 6. 테이블 생성

1. Workbench에서 `mongle_village` connection 접속
2. 상단 메뉴 `File` → `Open SQL Script` 클릭
3. 프로젝트 루트 폴더에서 `monggeul_village-2026-06-02.sql` 파일 선택
4. 열린 SQL 파일에서 ⚡ 버튼 클릭 (또는 `Cmd+Shift+Enter`)
5. 하단 **Output** 창에 오류 없이 완료되면 성공
6. 왼쪽 **Schemas** 패널에서 🔄 새로고침 버튼 클릭 → `mongle_village` 펼치면 테이블 15개 확인

> ⚠️ 이 SQL 파일 맨 앞에 **전체 테이블 삭제 구문**이 있습니다.
> 다시 실행하면 기존 데이터가 전부 삭제되니 주의하세요.

---

## 7. .env 설정

터미널에서 프로젝트 루트 폴더로 이동:

```bash
cd /Users/본인계정/Desktop/최종프로젝트/git_PJ/mongle-server
```

`.env.example` 파일을 `.env`로 복사:

```bash
cp .env.example .env
```

`.env` 파일을 텍스트 편집기로 열어서 아래 줄을 확인:

```
DATABASE_URL=mysql://mongle:mongle@localhost:3306/mongle_village
```

4단계에서 `mongle` 유저 비밀번호를 다르게 설정했다면 `mongle` 부분을 변경:
```
DATABASE_URL=mysql://mongle:변경한비밀번호@localhost:3306/mongle_village
```

---

## 8. Django 마이그레이션 동기화

테이블은 SQL로 이미 만들었으므로 Django에게 "테이블 이미 있어" 라고 알려주는 작업입니다.

터미널에서 프로젝트 루트 폴더 위치인지 확인 후 실행:

```bash
.venv/bin/python manage.py migrate --fake-initial
```

아래처럼 모든 항목이 `OK` 로 출력되면 완료:

```
Applying users.0001_initial... OK
Applying characters.0001_initial... OK
Applying todos.0001_initial... OK
...
```

---

## 테이블 목록

| 테이블 | 설명 |
|--------|------|
| `users` | 사용자 계정 |
| `social_accounts` | 소셜 로그인 연동 (카카오/구글/네이버) |
| `refresh_tokens` | 자동 로그인 토큰 |
| `characters` | 캐릭터 (계정당 최대 10명) |
| `tags` | 태그 |
| `todos` | TODO 항목 |
| `quests` | 퀘스트 |
| `schedules` | 캘린더 일정 |
| `posts` | SNS 게시물 (TODO 완료 시 자동 생성) |
| `comments` | 댓글 (토큰 3개 소모, 1일 최대 5개) |
| `replies` | 캐릭터 자동 답글 (댓글 10분 후) |
| `reflections` | 회고 |
| `token_transactions` | 토큰 거래 내역 |
| `notifications` | 알림 |
| `img_gen_logs` | 이미지 재생성 이력 (1일 3회 제한) |

---

## 문제 해결

**MySQL이 실행 안 될 때**

Mac 시스템 설정 → MySQL → **Start MySQL Server** 클릭

또는 터미널에서:
```bash
sudo /usr/local/mysql/support-files/mysql.server start
```

**`mysql: command not found` 오류**

3단계 PATH 설정이 안 된 것입니다. 3단계를 다시 실행하세요.

**`Access denied for user 'mongle'` 오류**

`.env`의 `DATABASE_URL`에 적힌 비밀번호와 MySQL `mongle` 유저 비밀번호가 다른 것입니다.
아래 명령어로 비밀번호를 `mongle`로 재설정:

```bash
mysql -u root -proot비밀번호 -e "ALTER USER 'mongle'@'localhost' IDENTIFIED BY 'mongle'; FLUSH PRIVILEGES;"
```

그리고 `.env`의 `DATABASE_URL`도 아래로 맞추기:
```
DATABASE_URL=mysql://mongle:mongle@localhost:3306/mongle_village
```

**테이블 전체 초기화하고 싶을 때**

Workbench에서 `monggeul_village-2026-06-02.sql` 을 다시 실행하면 전체 삭제 후 재생성됩니다.
이후 마이그레이션 재동기화도 필요합니다:
```bash
.venv/bin/python manage.py migrate --fake-initial
```
