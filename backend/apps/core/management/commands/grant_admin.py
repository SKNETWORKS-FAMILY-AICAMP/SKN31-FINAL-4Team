"""운영(ADMIN) 계정으로 승격한다.

    python manage.py grant_admin FEEDITADMIN            # 승격
    python manage.py grant_admin FEEDITADMIN --revoke   # 해제
    python manage.py grant_admin FEEDITADMIN --check    # 상태만 확인

무엇이 바뀌나
  auth_user.is_superuser = is_staff = True
    → /admin/ 관리자 화면 전체 권한
    → 화면 역할 role=admin · 요금제 plan=ADMIN (auth_views._user_payload)
    → 살!말? 카드·댓글을 누구 것이든 삭제 (신고 처리)
    → 직업 인증 심사 메뉴가 이 계정에만 보인다 (job.js JOB_REVIEW_DEMO=false)
  app_user.profile_metadata.plan = "ADMIN" 도 같이 적는다 (나중에 플랜을 표로 옮길 때 기준).
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import AppUser


class Command(BaseCommand):
    help = "계정을 운영(ADMIN · 슈퍼유저)으로 승격하거나 해제한다"

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--revoke", action="store_true")
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, **opts):
        name = opts["username"].strip()
        user = User.objects.filter(username__iexact=name).first()
        if user is None:
            raise CommandError(f"‘{name}’ 아이디를 찾지 못했습니다 (auth_user.username).")
        profile = AppUser.objects.filter(user=user).first()

        def show(prefix):
            meta = (profile.profile_metadata or {}) if profile else {}
            self.stdout.write(
                f"{prefix} {user.username} · 닉네임 {profile.nickname if profile else '(프로필 없음)'} · "
                f"superuser={user.is_superuser} staff={user.is_staff} · plan={meta.get('plan') or '-'}")

        if opts["check"]:
            show("현재")
            return
        on = not opts["revoke"]
        with transaction.atomic():
            user.is_superuser = on
            user.is_staff = on
            user.save(update_fields=["is_superuser", "is_staff"])
            if profile is not None:
                meta = dict(profile.profile_metadata or {})
                if on:
                    meta["plan"] = "ADMIN"
                elif meta.get("plan") == "ADMIN":
                    meta.pop("plan")
                profile.profile_metadata = meta
                profile.save(update_fields=["profile_metadata", "updated_at"])
        show("승격 완료" if on else "해제 완료")
