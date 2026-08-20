from django.core.management.base import BaseCommand

from apps.naver.models import TrendKeyword
from collection.naver.keywords import ALIASES, KEYWORDS


class Command(BaseCommand):
    help = "Create or update the initial NAVER fashion trend keywords."

    def handle(self, *args, **options):
        created = 0
        for category, names in KEYWORDS.items():
            for priority, name in enumerate(names):
                _, was_created = TrendKeyword.objects.update_or_create(
                    category=category,
                    name=name,
                    defaults={"aliases": ALIASES.get(name, []), "priority": priority, "is_active": True},
                )
                created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"NAVER 키워드 등록 완료: 신규 {created}개"))
