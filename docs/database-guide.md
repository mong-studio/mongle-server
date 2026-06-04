# 데이터베이스 세팅 가이드

> MySQL 9.7.0 + MySQL Workbench가 설치된 상태에서 진행합니다.

---

## 변경 내역

 - `schedules`, `reflections`, `token_transactions`, `notifications` Django 모델 추가
 - 가이드 간소화 (8단계 → 5단계), MySQL/Workbench 설치 섹션 제거

---

## 순서 요약

1. MySQL PATH 설정
2. DB 및 유저 생성
3. 테이블 생성
4. `.env` 설정
5. Django 마이그레이션 동기화

---

## 1. MySQL PATH 설정

터미널에서 한 번만 실행:

```bash
echo 'export PATH="/usr/local/mysql/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

확인:

```bash
mysql --version
```

`mysql  Ver 9.7.0 ...` 이 출력되면 완료.

---

## 2. DB 및 유저 생성

터미널 어디서든 실행 가능 `root비밀번호` 부분을 본인 MySQL root 비밀번호로 교체 후 실행:

```bash
mysql -u root -proot비밀번호 -e "
CREATE DATABASE IF NOT EXISTS mongle_village CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'mongle'@'localhost' IDENTIFIED BY 'mongle';
GRANT ALL PRIVILEGES ON mongle_village.* TO 'mongle'@'localhost';
FLUSH PRIVILEGES;
"
```

---

## 3. 테이블 생성

1. MySQL Workbench 실행 → `mongle_village` connection 접속
   - connection이 없으면: `+` 버튼 → Hostname `127.0.0.1` / Port `3306` / Username `root` / Default Schema `mongle_village` 입력 후 저장
2. `File` → `Open SQL Script` → 프로젝트 루트의 `monggeul_village-2026-06-02.sql` 선택
3. ⚡ 버튼으로 전체 실행
4. 왼쪽 Schemas 패널 🔄 새로고침 → 테이블 15개 확인

> ⚠️ 이 SQL 파일 맨 앞에 전체 테이블 삭제 구문이 있습니다. 재실행 시 기존 데이터가 모두 삭제됩니다.

---

## 4. .env 설정

```bash
cp .env.example .env
```

`.env` 파일에서 `mongle` 유저 비밀번호를 다르게 설정했다면 수정:

```
DATABASE_URL=mysql://mongle:변경한비밀번호@localhost:3306/mongle_village
```

---

## 5. Django 마이그레이션 동기화

프로젝트 루트에서 실행:

```bash
.venv/bin/python manage.py migrate --fake-initial
```

모든 항목이 `OK` 로 출력되면 완료.

---

## 문제 해결

**MySQL이 실행 안 될 때**

Mac 시스템 설정 → MySQL → **Start MySQL Server** 클릭

**`mysql: command not found` 오류**

1단계 PATH 설정을 다시 실행하세요.

**`Access denied for user 'mongle'` 오류**

`.env`의 비밀번호와 MySQL `mongle` 유저 비밀번호가 다른 것입니다:

```bash
mysql -u root -proot비밀번호 -e "ALTER USER 'mongle'@'localhost' IDENTIFIED BY 'mongle'; FLUSH PRIVILEGES;"
```

**테이블 전체 초기화**

Workbench에서 SQL 파일 다시 실행 후:

```bash
.venv/bin/python manage.py migrate --fake-initial
```
