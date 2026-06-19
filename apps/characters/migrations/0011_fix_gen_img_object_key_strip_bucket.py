"""0010 마이그레이션에서 path-style S3 URL 파싱 버그로 버킷명이 포함된
Character.gen_img_url 값을 올바른 object key 로 수정한다.

path-style URL: https://s3.region.amazonaws.com/bucket/key
→ 0010 추출 결과: bucket/key  (버킷명 포함 — 잘못됨)
→ 이번 수정:    key           (버킷명 제거 — 올바름)
"""

from __future__ import annotations

from django.conf import settings
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def fix_gen_img_object_key(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Character = apps.get_model("characters", "Character")
    User = apps.get_model("users", "User")

    bucket = getattr(settings, "AWS_S3_BUCKET", "")
    if not bucket:
        return  # S3 미설정 환경에서는 건너뜀

    prefix = f"{bucket}/"
    updated: dict[str, str] = {}

    for char in Character.objects.iterator():
        raw = char.gen_img_url or ""
        if not raw.startswith(prefix):
            continue  # 이미 올바른 값이거나 관련 없는 값

        new_key = raw[len(prefix) :]
        if new_key:
            char.gen_img_url = new_key
            char.save(update_fields=["gen_img_url"])
            updated[str(char.character_id)] = new_key

    # user.personalization["character"]["gen_img_url"] 도 동일하게 수정
    for user in User.objects.iterator():
        personalization = user.personalization
        if not isinstance(personalization, dict):
            continue
        character_data = personalization.get("character")
        if not isinstance(character_data, dict):
            continue

        char_id = character_data.get("character_id", "")
        if not char_id:
            continue

        if char_id in updated:
            new_key = updated[char_id]
        else:
            raw = character_data.get("gen_img_url", "")
            if not raw.startswith(prefix):
                continue
            new_key = raw[len(prefix) :]
            if not new_key:
                continue

        character_data["gen_img_url"] = new_key
        user.personalization = {**personalization, "character": character_data}
        user.save(update_fields=["personalization"])


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0010_backfill_gen_img_object_key"),
    ]

    operations = [
        migrations.RunPython(
            fix_gen_img_object_key,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
