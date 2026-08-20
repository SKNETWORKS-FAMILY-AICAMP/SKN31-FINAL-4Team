from django.core.management.base import BaseCommand, CommandError

from collection.naver.locking import CollectionAlreadyRunning, naver_collection_lock
from collection.naver.services import collect_blog, collect_search_trends, collect_shopping_trends


class Command(BaseCommand):
    help = "Collect NAVER API HUB blog and trend data for 10대, 20대, 30대."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=["all", "blog", "search-trend", "shopping"], default="all")

    def handle(self, *args, **options):
        source = options["source"]
        try:
            with naver_collection_lock():
                if source in {"all", "blog"}:
                    self.stdout.write(f"[NAVER BLOG] {collect_blog()}")
                if source in {"all", "search-trend"}:
                    self.stdout.write(f"[NAVER SEARCH TREND] {collect_search_trends()}")
                if source in {"all", "shopping"}:
                    self.stdout.write(f"[NAVER SHOPPING] {collect_shopping_trends()}")
        except (CollectionAlreadyRunning, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
