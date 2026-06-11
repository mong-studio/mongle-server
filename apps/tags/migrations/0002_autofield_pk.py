from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tags", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="tag",
            name="tag_id",
            field=models.AutoField(primary_key=True, serialize=False),
        )
    ]
