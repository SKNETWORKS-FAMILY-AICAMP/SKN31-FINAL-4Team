from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0055_salmal_real_data_fields")]

    operations = [
        migrations.CreateModel(
            name="VoteReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_type", models.CharField(choices=[("CARD", "카드"), ("COMMENT", "댓글")], max_length=10, verbose_name="신고 대상")),
                ("target_id", models.PositiveBigIntegerField(verbose_name="신고 대상 ID")),
                ("reason", models.CharField(blank=True, default="", max_length=500, verbose_name="신고 사유")),
                ("target_snapshot", models.JSONField(blank=True, default=dict, verbose_name="대상 스냅샷")),
                ("status", models.CharField(choices=[("PENDING", "검토 대기"), ("REVIEWED", "검토 완료"), ("DISMISSED", "기각")], default="PENDING", max_length=20, verbose_name="처리 상태")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="신고일시")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="수정일시")),
                ("card", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reports", to="core.votecard", verbose_name="대상 카드")),
                ("comment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reports", to="core.votecomment", verbose_name="대상 댓글")),
                ("reporter", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="vote_reports", to="core.appuser", verbose_name="신고자")),
            ],
            options={
                "verbose_name": "살말 신고",
                "verbose_name_plural": "살말 신고",
                "db_table": '"app"."vote_report"',
                "indexes": [
                    models.Index(fields=["target_type", "target_id"], name="idx_vote_report_target"),
                    models.Index(fields=["status", "-created_at"], name="idx_vote_report_status"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("reporter", "target_type", "target_id"), name="uq_vote_report_target"),
                ],
            },
        ),
    ]
