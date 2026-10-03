from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.dashboard.models import DashboardOTPDevice


class Command(BaseCommand):
    help = "분실한 관리자 인증 앱 연결과 복구 코드를 초기화합니다."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        username = options["username"]
        user = get_user_model().objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"사용자를 찾을 수 없습니다: {username}")
        if not (user.is_staff or user.is_superuser):
            raise CommandError("운영 계정이 아닌 사용자는 초기화할 수 없습니다.")
        deleted, _ = DashboardOTPDevice.objects.filter(user=user).delete()
        if deleted:
            self.stdout.write(self.style.SUCCESS(f"{username}의 관리자 OTP를 초기화했습니다."))
        else:
            self.stdout.write(self.style.WARNING(f"{username}에 연결된 관리자 OTP가 없습니다."))
