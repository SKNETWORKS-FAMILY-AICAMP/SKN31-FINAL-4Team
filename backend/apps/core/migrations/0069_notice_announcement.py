# 2026-10-02 — 운영 공지 알림 · 성별 요청 알림 종류, 실시간 공지(상단 띠) 표.
#
# ★ 손으로 쓴 마이그레이션이다. makemigrations 를 그대로 돌리면 다른 작업자의 모델 변경
#   (상품 관계 표 · 제약 정리 등)이 한꺼번에 딸려 들어온다 — 이 변경에 필요한 두 가지만 담는다.
#   · notification.kind 선택지 두 개 추가 (DB 에는 아무 변화 없음 — choices 는 Django 쪽 검사다)
#   · app.announcement 표 생성
#
# 적용:  python manage.py migrate core 0069 --plan   (확인)  →  python manage.py migrate core 0069

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0068_cleanup_legacy_text_mention_fields"),
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
                ],
                max_length=30,
                verbose_name="알림 종류",
            ),
        ),
        migrations.CreateModel(
            name="Announcement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.CharField(max_length=140, verbose_name="공지 문구")),
                ("link", models.CharField(blank=True, default="", max_length=200, verbose_name="이동 화면")),
                ("starts_at", models.DateTimeField(default=django.utils.timezone.now, verbose_name="시작")),
                ("ends_at", models.DateTimeField(blank=True, null=True, verbose_name="종료")),
                ("active", models.BooleanField(default=True, verbose_name="게시 중")),
                ("created_by", models.CharField(blank=True, default="", max_length=150, verbose_name="올린 사람")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="생성일시")),
            ],
            options={
                "verbose_name": "실시간 공지",
                "verbose_name_plural": "실시간 공지",
                "db_table": '"app"."announcement"',
                "indexes": [models.Index(fields=["active", "starts_at"], name="idx_announce_live")],
            },
        ),
    ]
