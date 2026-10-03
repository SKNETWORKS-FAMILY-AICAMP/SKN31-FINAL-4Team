# 직업 인증 결과 알림 (2026-09-19) — Notification.kind 에 JOB_REVIEW 추가, 알림 설정에 job_review 칸 추가.
# 적용: python manage.py migrate core 0060
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0059_notification_soft_delete'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='kind',
            field=models.CharField(choices=[('PRICE_DROP', '찜한 상품 가격 하락'), ('VOTE_RESULT', '살!말? 투표 결과'), ('WEEKLY_REPORT', '주간 트렌드 리포트'), ('BADGE', '뱃지 달성'), ('TERM_ADDED', '용어 사전 등재'), ('JOB_REVIEW', '직업 인증 결과')], max_length=30, verbose_name='알림 종류'),
        ),
        migrations.AddField(
            model_name='notificationsetting',
            name='job_review',
            field=models.BooleanField(default=True, verbose_name='직업 인증 결과'),
        ),
    ]
