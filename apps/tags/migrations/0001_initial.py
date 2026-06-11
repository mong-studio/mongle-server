"""tags 테이블은 apps.todos 0001에서 생성됨.
SeparateDatabaseAndState로 앱 이동만 수행한다."""

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("todos", "0001_initial")]

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
                        ("content", models.CharField(max_length=20)),
                        ("color", models.CharField(max_length=7)),
                    ],
                    options={"db_table": "tags"},
                )
            ],
            database_operations=[],
        )
    ]
