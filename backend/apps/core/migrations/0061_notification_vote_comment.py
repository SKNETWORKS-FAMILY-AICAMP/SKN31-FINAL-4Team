# 살!말? 새 댓글 알림 (2026-09-19) — Notification.kind 에 VOTE_COMMENT, 알림 설정에 vote_comment 칸.
# 적용: python manage.py migrate core 0061
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0060_notification_job_review'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='kind',
            field=models.CharField(choices=[('PRICE_DROP', '찜한 상품 가격 하락'), ('VOTE_RESULT', '살!말? 투표 결과'), ('WEEKLY_REPORT', '주간 트렌드 리포트'), ('BADGE', '뱃지 달성'), ('TERM_ADDED', '용어 사전 등재'), ('JOB_REVIEW', '직업 인증 결과'), ('VOTE_COMMENT', '살!말? 새 댓글')], max_length=30, verbose_name='알림 종류'),
        ),
        migrations.AddField(
            model_name='notificationsetting',
            name='vote_comment',
            field=models.BooleanField(default=True, verbose_name='살!말? 새 댓글'),
        ),
    ]
