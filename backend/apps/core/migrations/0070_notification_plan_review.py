# 2026-10-03 — 요금제 신청 결과 알림 종류 하나 (apps/api/plan_views.py).
#
# ★ 손으로 쓴 마이그레이션이다 (0069 와 같은 이유 — makemigrations 를 그대로 돌리면
#   다른 작업자의 모델 변경이 한꺼번에 딸려 들어온다).
#   · notification.kind 선택지 PLAN_REVIEW 추가 — DB 에는 아무 변화 없음(choices 는 Django 쪽 검사다)
#   · 요금제 자체는 app_user.profile_metadata 에 둔다. 새 표 · 새 칸이 없다.
#
# 적용:  python manage.py migrate core 0070 --plan   (확인)  →  python manage.py migrate core 0070

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0069_notice_announcement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("PRICE_DROP", "찜한 상품 가격 하락"),
                    ("VOTE_RESULT", "살!말? 투표 결과"),
                    ("WEEKLY_REPORT", "주간 트렌드 리포트"),
                    ("BADGE", "뱃지 달성"),
                    ("TERM_ADDED", "용어 사전 등재"),
                    ("JOB_REVIEW", "직업 인증 결과"),
                    ("VOTE_COMMENT", "살!말? 새 댓글"),
                    ("OPS_ALERT", "운영 알림"),
                    ("ADMIN_NOTICE", "운영 공지"),
                    ("PROFILE_GENDER", "프로필 정보 요청"),
                    ("PLAN_REVIEW", "요금제 신청 결과"),
                ],
                max_length=30,
                verbose_name="알림 종류",
            ),
        ),
    ]
