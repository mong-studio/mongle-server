"""기본 태그 시드 (no-op).

Tag.user 가 NOT NULL 로 유저별 분리(#28)되면서 user 없는 전역 시드는
적용할 수 없고, 기본 태그 자동 부여 기능 자체를 폐지했다. 태그는 항상
클라이언트가 명시한다. 마이그레이션 그래프 유지를 위해 파일/의존성은
보존하되 동작은 no-op 이다.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("tags", "0002_autofield_pk")]

    operations = []
