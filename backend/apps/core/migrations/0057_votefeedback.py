# 살!말? 사후 피드백 표 (2026-09-19) — app.vote_feedback
# 수동 작성. 적용: python manage.py migrate core 0057
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0056_votereport")]

    operations = [
        migrations.CreateModel(
            name="VoteFeedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("purchase", models.CharField(choices=[("BOUGHT", "샀어요"), ("SKIPPED", "안 샀어요"), ("UNDECIDED", "아직 고민 중")], max_length=20, verbose_name="구매 여부")),
                ("satisfaction", models.PositiveSmallIntegerField(blank=True, null=True, help_text="샀으면 '사길 잘했나', 안 샀으면 '안 사길 잘했나'. 고민 중이면 비워 둔다.", verbose_name="만족도(1~5)")),
                ("helpful", models.BooleanField(blank=True, null=True, verbose_name="투표가 도움이 됐나")),
                ("comment", models.CharField(blank=True, default="", max_length=300, verbose_name="한 줄 후기")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="작성일시")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="수정일시")),
                ("card", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="feedback", to="core.votecard", verbose_name="카드")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="vote_feedbacks", to="core.appuser", verbose_name="작성자")),
            ],
            options={
                "verbose_name": "살말 피드백",
                "verbose_name_plural": "살말 피드백",
                "db_table": '"app"."vote_feedback"',
                "indexes": [
                    models.Index(fields=["user", "-created_at"], name="idx_vote_feedback_user"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("satisfaction__isnull", True), models.Q(("satisfaction__gte", 1), ("satisfaction__lte", 5)), _connector="OR"),
                        name="ck_vote_feedback_satisfaction",
                    ),
                ],
            },
        ),
    ]
