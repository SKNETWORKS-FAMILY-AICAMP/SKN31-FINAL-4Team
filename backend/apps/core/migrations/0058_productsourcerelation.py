import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0057_merge_productreview_vote"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductSourceRelation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "relation_type",
                    models.CharField(
                        choices=[("RESALE_OF", "중고 매물의 원상품")],
                        max_length=50,
                    ),
                ),
                (
                    "evidence_source",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "from_product_source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outgoing_relations",
                        to="core.productsource",
                    ),
                ),
                (
                    "to_product_source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incoming_relations",
                        to="core.productsource",
                    ),
                ),
            ],
            options={
                "db_table": '"commerce"."product_source_relation"',
                "indexes": [
                    models.Index(
                        fields=["from_product_source", "relation_type"],
                        name="idx_prod_src_rel_from",
                    ),
                    models.Index(
                        fields=["to_product_source", "relation_type"],
                        name="idx_prod_src_rel_to",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "from_product_source",
                            "to_product_source",
                            "relation_type",
                        ),
                        name="uq_product_source_relation",
                    ),
                ],
            },
        ),
    ]
