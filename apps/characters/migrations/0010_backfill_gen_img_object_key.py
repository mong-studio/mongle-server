"""기존 Character.gen_img_url 을 presigned URL에서 S3 object key로 변환한다.

origin_img_url 과 동일한 패턴으로 저장해 조회 시점에 재서명하도록 한다.
CharacterGenerationJob.gen_img_object_key 를 우선 사용하고, 없으면 URL path 에서 추출
user.personalization["character"]["gen_img_url"] 도 같은 값으로 업데이트한다.
"""

from __future__ import annotations

from urllib.parse import urlparse

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def _extract_key_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return url  # 이미 object key
    if parsed.hostname and parsed.hostname.endswith(".amazonaws.com"):
        return parsed.path.lstrip("/")
    return url


def backfill_gen_img_object_key(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Character = apps.get_model("characters", "Character")
    User = apps.get_model("users", "User")

    # character_id → new_key 맵 (personalization 업데이트용)
    updated: dict[str, str] = {}

    for char in Character.objects.select_related("generation_job").iterator():
        raw = char.gen_img_url or ""
        parsed = urlparse(raw)

        # 이미 object key 형태(http 아님)이면 건너뜀
        if parsed.scheme not in ("http", "https"):
            continue

        job = char.generation_job
        if job and job.gen_img_object_key:
            new_key = job.gen_img_object_key
        else:
            new_key = _extract_key_from_url(raw)

        if new_key and new_key != raw:
            char.gen_img_url = new_key
            char.save(update_fields=["gen_img_url"])
            updated[str(char.character_id)] = new_key

    # user.personalization["character"]["gen_img_url"] 도 object key 로 업데이트
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

        # 이미 업데이트한 캐릭터면 새 key 사용, 아니면 현재 DB 값 읽기
        if char_id in updated:
            new_key = updated[char_id]
        else:
            try:
                char = Character.objects.get(character_id=char_id)
                raw = char.gen_img_url or ""
                parsed = urlparse(raw)
                if parsed.scheme in ("http", "https"):
                    new_key = _extract_key_from_url(raw)
                else:
                    continue  # 이미 object key
            except Character.DoesNotExist:
                continue

        if new_key and new_key != character_data.get("gen_img_url"):
            character_data["gen_img_url"] = new_key
            user.personalization = {**personalization, "character": character_data}
            user.save(update_fields=["personalization"])


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0009_remove_charactergenerationjob_error_code_and_more"),
        ("users", "0007_merge_0006_notification_data_0006_user_personalization"),
    ]

    operations = [
        migrations.RunPython(
            backfill_gen_img_object_key,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
