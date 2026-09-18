from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0054_votecomment_saved_constraints_seed_cards")]

    operations = [
        migrations.AddField(
            model_name="votecard",
            name="product_source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="vote_cards",
                to="core.productsource",
                verbose_name="상품 출처",
            ),
        ),
        migrations.AddField(
            model_name="votecard",
            name="seed_key",
            field=models.CharField(blank=True, max_length=160, null=True, unique=True, verbose_name="시드 식별자"),
        ),
        migrations.AddField(
            model_name="votecard",
            name="gender_target",
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name="성별 타깃"),
        ),
        migrations.AddField(
            model_name="votecard",
            name="closes_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="마감일시"),
        ),
        migrations.AddField(
            model_name="votecard",
            name="source_metadata",
            field=models.JSONField(blank=True, default=dict, verbose_name="출처 메타데이터"),
        ),
        migrations.AddField(
            model_name="votecomment",
            name="seed_key",
            field=models.CharField(blank=True, max_length=190, null=True, unique=True, verbose_name="시드 식별자"),
        ),
        migrations.AddField(
            model_name="votecomment",
            name="choice",
            field=models.CharField(
                blank=True,
                choices=[("BUY", "살"), ("PASS", "말"), ("NEUTRAL", "중립")],
                max_length=10,
                null=True,
                verbose_name="댓글 의견",
            ),
        ),
        migrations.AddField(
            model_name="votecomment",
            name="source_metadata",
            field=models.JSONField(blank=True, default=dict, verbose_name="출처 메타데이터"),
        ),
        migrations.AddIndex(
            model_name="votecard",
            index=models.Index(fields=["gender_target", "status"], name="idx_vote_gender_status"),
        ),
    ]
