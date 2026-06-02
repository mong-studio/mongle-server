# Mongle Server 프로젝트 가이드

이 문서는 프로젝트 구조와 개발 원칙을 설명합니다.

설치와 실행 방법은 [setup-guide.md](setup-guide.md)를 확인해 주세요.
Git 최신화, 커밋, PR 작성 방법은 [git-strategy.md](git-strategy.md)를 확인해 주세요.
데이터베이스 세팅은 [database-guide.md](database-guide.md)를 확인해 주세요.

## 기본 원칙

- 이 프로젝트는 `uv` 기반입니다. `requirements.txt` 같은 별도 의존성 파일은 만들지 않습니다.
- Django 앱은 `apps/` 아래에 만듭니다.
- Django 설정은 `config.settings.*`를 사용합니다.
- 여러 앱이 같이 쓰는 코드는 `common/`에 둡니다.
- 외부 서비스와 가까운 코드는 `infrastructure/`에 둡니다.
- 프로젝트 구조, 실행 방법, CI, 런타임 동작이 바뀌면 문서도 같이 업데이트합니다.

## 폴더 구조

| 폴더 | 역할 |
| --- | --- |
| `config/` | Django 설정, URL, ASGI/WSGI 진입점 |
| `apps/` | 우리가 만드는 Django 앱 |
| `common/` | 여러 앱이 공유하는 공통 코드 |
| `infrastructure/` | 이메일, 저장소, 외부 서비스 연동 코드 |
| `tests/` | pytest 테스트 코드 |
| `docs/` | 팀원이 읽는 문서 |

## 코드를 어디에 둘까요?

새 기능을 만들 때는 먼저 어떤 책임인지 생각합니다.

| 상황 | 위치 |
| --- | --- |
| 새로운 Django 앱 | `apps/새앱이름/` |
| 특정 앱의 API view | `apps/해당앱/views.py` |
| 특정 앱의 serializer | `apps/해당앱/serializers.py` |
| 특정 앱의 model | `apps/해당앱/models.py` |
| 여러 앱에서 같이 쓰는 pagination, permission, exception | `common/` |
| 이메일, 파일 저장소, 외부 API 연동 | `infrastructure/` |
| 프로젝트 URL 또는 설정 변경 | `config/` |
| 테스트 | `tests/` |

## 개발할 때 확인할 것

- 변경하려는 파일이 이번 작업의 목적과 관련 있는지 확인합니다.
- 모델을 바꿨다면 migration이 필요한지 확인합니다.
- API 동작, serializer, permission, validation이 바뀌면 테스트를 추가하거나 수정합니다.
- 팀원이 이해해야 하는 구조 변경은 문서에 남깁니다.
- 공통 코드로 빼기 전에 정말 여러 곳에서 쓰이는지 확인합니다.

## 막혔을 때

혼자 오래 붙잡고 있기보다 아래 정보를 정리해서 팀원에게 공유합니다.

- 무엇을 하려고 했는지
- 어떤 명령어를 실행했는지
- 어떤 에러가 났는지
- 이미 시도해 본 해결 방법은 무엇인지

좋은 질문 예:

```text
Todo 모델에 due_date를 추가하려고 했습니다.
uv run python manage.py makemigrations 실행 중 아래 에러가 납니다.
에러 메시지:
...
제가 확인한 것은 .env의 DATABASE_URL과 앱 등록 여부입니다.
```
