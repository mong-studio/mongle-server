from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0012_remove_character_gen_img_object_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="character",
            name="appearance_payload",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="charactergenerationjob",
            name="appearance_payload",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
