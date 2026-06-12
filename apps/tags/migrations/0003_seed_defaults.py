"""기본 태그 시드 (no-op).

Tag.user 가 NOT NULL 로 유저별 분리(#28)되면서, user 없는 전역 시드는
더 이상 적용할 수 없다. 기본 태그는 회원가입 시 유저별로 생성해야 한다
(후속 작업). DEFAULT_TAGS 는 그 시딩에 재사용할 수 있도록 남겨 둔다.
마이그레이션 그래프 유지를 위해 파일/의존성은 보존하되 동작은 no-op 이다.
"""

from __future__ import annotations

from django.db import migrations

# 회원가입 시 유저별 기본 태그 생성에 재사용 (content, color)
DEFAULT_TAGS = [
    ("일반", "#8e6038"),
    ("업무", "#4b7bec"),
    ("건강", "#26de81"),
    ("공부", "#f7b731"),
    ("취미", "#fd9644"),
    ("약속", "#a29bfe"),
]


class Migration(migrations.Migration):
    dependencies = [("tags", "0002_autofield_pk")]

    operations = []
