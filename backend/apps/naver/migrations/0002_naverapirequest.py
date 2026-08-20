from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("naver", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="NaverApiRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(max_length=30)),
                ("request_hash", models.CharField(max_length=64)),
                ("collection_date", models.DateField()),
                ("completed_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="naverapirequest",
            index=models.Index(fields=["source", "collection_date"], name="naver_api_request_day_idx"),
        ),
        migrations.AddConstraint(
            model_name="naverapirequest",
            constraint=models.UniqueConstraint(
                fields=("source", "request_hash", "collection_date"),
                name="naver_unique_api_request",
            ),
        ),
    ]
