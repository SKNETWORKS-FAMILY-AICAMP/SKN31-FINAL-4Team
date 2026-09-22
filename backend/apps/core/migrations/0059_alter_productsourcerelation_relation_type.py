from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0058_productsourcerelation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productsourcerelation",
            name="relation_type",
            field=models.CharField(
                choices=[
                    ("RESALE_OF", "중고 매물의 원상품"),
                    ("RELATED_USED", "관련 중고 매물"),
                ],
                max_length=50,
            ),
        ),
    ]
