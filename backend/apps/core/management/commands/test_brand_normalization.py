from django.core.management.base import BaseCommand

from apps.core.models import (
    Brand,
    BrandSource,
    CrawlRun,
    DictionaryTerm,
    MappingCandidate,
    TermAlias,
)

from apps.core.services.normalization import (
    normalize_musinsa_brands_from_crawl_run,
)


class Command(BaseCommand):
    help = "무신사 브랜드 정규화 테스트"

    def add_arguments(self, parser):
        parser.add_argument(
            "--run-id",
            type=int,
            required=False,
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "=== FEEDIT Brand Normalization Test ==="
            )
        )

        self.stdout.write("\n[DB COUNT]")

        self.stdout.write(
            f"Brand: {Brand.objects.count()}"
        )

        self.stdout.write(
            f"BrandSource: {BrandSource.objects.count()}"
        )

        self.stdout.write(
            (
                "DictionaryTerm(BRAND): "
                f"{DictionaryTerm.objects.filter(term_type='BRAND').count()}"
            )
        )

        self.stdout.write(
            (
                "TermAlias(BRAND): "
                f"{TermAlias.objects.filter(term__term_type='BRAND').count()}"
            )
        )

        self.stdout.write(
            (
                "MappingCandidate(BRAND): "
                f"{MappingCandidate.objects.filter(mapping_type='BRAND').count()}"
            )
        )

        run_id = options.get("run_id")

        if not run_id:
            latest_run = (
                CrawlRun.objects
                .filter(
                    source__code__iexact="MUSINSA",
                    status=CrawlRun.Status.SUCCESS,
                )
                .order_by("-id")
                .first()
            )

            if not latest_run:
                self.stdout.write(
                    self.style.ERROR(
                        "MUSINSA SUCCESS CrawlRun이 없습니다."
                    )
                )
                return

            run_id = latest_run.id

            self.stdout.write(
                self.style.WARNING(
                    f"run-id 미지정 → 최신 CrawlRun #{run_id} 사용"
                )
            )

        self.stdout.write(
            f"\n[NORMALIZE] CrawlRun #{run_id}"
        )

        result = (
            normalize_musinsa_brands_from_crawl_run(
                crawl_run_id=run_id,
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nResult: {result}"
            )
        )

        self.stdout.write(
            "\n[MAPPED BRANDS]"
        )

        mappings = (
            BrandSource.objects
            .select_related(
                "brand",
                "source",
            )
            .filter(
                source__code__iexact="MUSINSA",
            )
            .order_by("-id")[:20]
        )

        for item in mappings:
            self.stdout.write(
                (
                    f"{item.source.code} | "
                    f"{item.source_brand_id} | "
                    f"{item.source_brand_name} "
                    f"-> {item.brand.name}"
                )
            )

        self.stdout.write(
            "\n[UNMAPPED BRANDS]"
        )

        candidates = (
            MappingCandidate.objects
            .filter(
                source__code__iexact="MUSINSA",
                mapping_type="BRAND",
                status="PENDING",
            )
            .order_by("-detected_count")[:20]
        )

        for item in candidates:
            self.stdout.write(
                (
                    f"{item.source_key} | "
                    f"{item.source_name} | "
                    f"count={item.detected_count}"
                )
            )