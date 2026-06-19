"""characters 테이블에서 gen_img_object_key 컬럼을 제거한다.

이전 세션에서 Character 모델에 gen_img_object_key 필드가 추가됐다가
gen_img_url 에 object key 를 직접 저장하는 방식으로 변경되면서 모델에서 제거됐지만
DB 컬럼은 남아 있어 Character.objects.create() 시 MySQL 1364 에러가 발생했다.

SQLite(테스트 DB)에는 해당 컬럼이 처음부터 없으므로 MySQL 에서만 DROP 을 실행한다.
"""

from __future__ import annotations

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def drop_column_if_exists(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.columns"
            " WHERE table_schema = DATABASE()"
            " AND table_name = 'characters'"
            " AND column_name = 'gen_img_object_key'"
        )
        if cursor.fetchone()[0]:
            cursor.execute("ALTER TABLE characters DROP COLUMN gen_img_object_key")


def restore_column(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE characters ADD COLUMN"
            " gen_img_object_key VARCHAR(500) NOT NULL DEFAULT ''"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0011_fix_gen_img_object_key_strip_bucket"),
    ]

    operations = [
        migrations.RunPython(drop_column_if_exists, reverse_code=restore_column),
    ]
