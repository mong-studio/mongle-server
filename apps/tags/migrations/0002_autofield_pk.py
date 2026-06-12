"""tag_id 상태를 AutoField 로 정리(상태 전용).

실제 AUTO_INCREMENT 는 todos.0001 의 테이블 생성 시점에 부여된다. 여기서
DB 를 변경하면 todos/schedules 의 FK 가 tag_id 를 참조하고 있어 MySQL 이
컬럼 변경을 거부(1833)하므로, 상태만 모델과 일치시킨다.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tags", "0001_initial")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="tag",
                    name="tag_id",
                    field=models.AutoField(primary_key=True, serialize=False),
                )
            ],
            database_operations=[],
        )
    ]
