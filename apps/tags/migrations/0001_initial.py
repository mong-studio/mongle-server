"""tags 테이블은 apps.todos 0001에서 생성되고, 0004에서 user 컬럼/제약이 추가됨.
SeparateDatabaseAndState로 모델 소유권만 apps.tags로 이동한다(DB 변경 없음)."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("todos", "0004_tag_user_tag_unique_user_tag"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Tag",
                    fields=[
                        (
                            "tag_id",
                            models.IntegerField(primary_key=True, serialize=False),
                        ),
                        (
                            "user",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="tags",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        ("content", models.CharField(max_length=20)),
                        ("color", models.CharField(max_length=7)),
                    ],
                    options={
                        "db_table": "tags",
                        "constraints": [
                            models.UniqueConstraint(
                                fields=("user", "content"), name="unique_user_tag"
                            )
                        ],
                    },
                )
            ],
            database_operations=[],
        )
    ]
