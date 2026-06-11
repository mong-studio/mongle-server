from django.db import models


class Tag(models.Model):
    tag_id = models.AutoField(primary_key=True)
    content = models.CharField(max_length=20)
    color = models.CharField(max_length=7)

    class Meta:
        db_table = "tags"
