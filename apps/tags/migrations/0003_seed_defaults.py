from __future__ import annotations

from typing import Any

from django.db import migrations

DEFAULT_TAGS = [
    (1, "일반", "#8e6038"),
    (2, "업무", "#4b7bec"),
    (3, "건강", "#26de81"),
    (4, "공부", "#f7b731"),
    (5, "취미", "#fd9644"),
    (6, "약속", "#a29bfe"),
]


def seed_tags(apps: Any, schema_editor: Any) -> None:
    Tag = apps.get_model("tags", "Tag")
    for tag_id, content, color in DEFAULT_TAGS:
        Tag.objects.get_or_create(
            tag_id=tag_id, defaults={"content": content, "color": color}
        )


class Migration(migrations.Migration):
    dependencies = [("tags", "0002_autofield_pk")]

    operations = [migrations.RunPython(seed_tags, migrations.RunPython.noop)]
