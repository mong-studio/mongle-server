"""apps.todos.Tag → apps.tags.Tag 앱 이동 (상태 전환만, DB 변경 없음)."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("todos", "0003_reflection_schedule"),
        ("tags", "0003_seed_defaults"),
    ]

    operations = [
        # Tag 모델을 todos 상태에서 제거 (DB 변경 없음 — tags 앱이 관리)
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel("Tag")],
            database_operations=[],
        ),
        # FK 참조를 todos.Tag → tags.Tag 로 업데이트 (DB 변경 없음 — 테이블명 동일)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="todo",
                    name="tag",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="todos",
                        to="tags.tag",
                    ),
                ),
                migrations.AlterField(
                    model_name="schedule",
                    name="tag",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="schedules",
                        to="tags.tag",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
