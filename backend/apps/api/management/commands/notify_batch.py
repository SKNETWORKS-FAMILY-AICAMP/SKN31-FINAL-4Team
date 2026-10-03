"""알림 배치를 손으로 돌린다 — Celery beat 없이 확인할 때 쓴다.

    python manage.py notify_batch --daily
    python manage.py notify_batch --weekly
    python manage.py notify_batch --daily --weekly

같은 날 두 번 돌려도 알림은 한 번만 생긴다 (Notification.dedup_key).
"""
from django.core.management.base import BaseCommand

from apps.api import notification_service


class Command(BaseCommand):
    help = "알림 배치(일·주)를 실행한다."

    def add_arguments(self, parser):
        parser.add_argument("--daily", action="store_true", help="가격 하락 · 용어 사전 등재")
        parser.add_argument("--weekly", action="store_true", help="주간 트렌드 리포트")

    def handle(self, *args, **options):
        if not options["daily"] and not options["weekly"]:
            self.stderr.write("--daily 또는 --weekly 중 하나는 있어야 합니다.")
            return
        if options["daily"]:
            made = notification_service.run_daily()
            self.stdout.write(f"일 배치 — 가격 하락 {made['price_drop']}건 · "
                              f"용어 등재 {made['term_added']}건")
        if options["weekly"]:
            made = notification_service.run_weekly()
            self.stdout.write(f"주 배치 — 주간 리포트 {made['weekly_report']}건")
