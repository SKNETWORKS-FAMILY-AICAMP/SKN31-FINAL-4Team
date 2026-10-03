from __future__ import annotations

import time
from dataclasses import dataclass, field

from apps.core.models import Brand, ProductSource

from .pipeline import ProductNormalizationPipeline


# ============================================================
# Result
# ============================================================


@dataclass
class BrandNormalizationResult:
    brand_id: int
    brand_name: str

    total: int = 0
    processed: int = 0

    changed: int = 0
    unchanged: int = 0
    empty: int = 0
    failed: int = 0

    failed_rows: list[dict] = field(
        default_factory=list
    )

    elapsed_seconds: float = 0.0


# ============================================================
# Runner
# ============================================================


class BrandProductNormalizationRunner:
    """
    특정 FEEDIT Brand에 연결된 모든 ProductSource를 대상으로
    STEP02 V2 상품명 정규화를 실행한다.

    Flow
    ----
    Brand
        -> Product
        -> ProductSource
        -> source_name
        -> ProductNormalizationPipeline
        -> core_name
        -> ProductSource.normalized_name

    Important
    ---------
    - 입력은 항상 source_name이다.
    - 기존 normalized_name은 입력으로 절대 사용하지 않는다.
    - 기존 normalized_name은 변경 여부 비교에만 사용한다.
    - source_name은 절대 수정하지 않는다.
    - 최종 core_name을 normalized_name에 저장한다.
    - 빈 core_name은 저장하지 않는다.
    - source별 Pipeline은 한 번만 초기화하여 재사용한다.
    """

    def __init__(
        self,
        *,
        save: bool = False,
        batch_size: int = 500,
        print_every: int = 50,
        print_changes: bool = True,
        print_removed: bool = True,
    ):
        self.save = save
        self.batch_size = batch_size
        self.print_every = print_every
        self.print_changes = print_changes
        self.print_removed = print_removed

        self._pipelines: dict[
            str,
            ProductNormalizationPipeline,
        ] = {}

    # ========================================================
    # Public
    # ========================================================

    def run(
        self,
        brand_id: int,
    ) -> BrandNormalizationResult:

        brand = Brand.objects.get(
            id=brand_id,
        )

        queryset = self._get_queryset(
            brand_id=brand_id,
        )

        total = queryset.count()

        result = BrandNormalizationResult(
            brand_id=brand.id,
            brand_name=str(brand),
            total=total,
        )

        self._print_header(
            brand=brand,
            total=total,
        )

        started_at = time.perf_counter()

        for product_source in queryset.iterator(
            chunk_size=self.batch_size,
        ):
            self._process_one(
                product_source=product_source,
                result=result,
            )

            if (
                result.processed % self.print_every == 0
                or result.processed == total
            ):
                self._print_progress(
                    result=result,
                    started_at=started_at,
                )

        result.elapsed_seconds = (
            time.perf_counter()
            - started_at
        )

        self._print_summary(
            result=result,
        )

        return result

    # ========================================================
    # Query
    # ========================================================

    @staticmethod
    def _get_queryset(
        *,
        brand_id: int,
    ):
        """
        해당 FEEDIT Brand로 정규화된 BrandSource에 속한
        모든 ProductSource를 조회한다.

        Product 매핑 여부와 관계없이 처리한다.
        """

        return (
            ProductSource.objects
            .filter(
                source_brand__brand_id=brand_id,
            )
            .select_related(
                "source",
                "product",
                "source_brand",
            )
            .order_by("id")
            .distinct()
        )

    # ========================================================
    # Pipeline
    # ========================================================

    def _get_pipeline(
        self,
        source_code: str,
    ) -> ProductNormalizationPipeline:

        pipeline = self._pipelines.get(
            source_code
        )

        if pipeline is not None:
            return pipeline

        print(
            f"\nPipeline 초기화: {source_code}"
        )

        pipeline = ProductNormalizationPipeline(
            source_code=source_code,
        )

        self._pipelines[source_code] = pipeline

        return pipeline

    # ========================================================
    # Input
    # ========================================================

    @staticmethod
    def _get_source_name(
        product_source: ProductSource,
    ) -> str:
        """
        STEP02 V2의 입력은 무조건 source_name.

        기존 normalized_name은 입력으로 사용하지 않는다.
        """

        return (
            product_source.source_name
            or ""
        ).strip()

    # ========================================================
    # Process
    # ========================================================

    def _process_one(
        self,
        *,
        product_source: ProductSource,
        result: BrandNormalizationResult,
    ) -> None:

        result.processed += 1

        source_code = (
            product_source.source.code
        )

        try:
            # ------------------------------------------------
            # Original source name
            # ------------------------------------------------

            source_name = self._get_source_name(
                product_source
            )

            old_normalized_name = (
                product_source.normalized_name
                or ""
            ).strip()

            # ------------------------------------------------
            # Empty source_name
            # ------------------------------------------------

            if not source_name:
                result.empty += 1

                print(
                    "\n[EMPTY SOURCE NAME]"
                    f" ID={product_source.id}"
                    f" SOURCE={source_code}"
                )

                return

            # ------------------------------------------------
            # Pipeline
            # ------------------------------------------------

            pipeline = self._get_pipeline(
                source_code
            )

            pipeline_result = self._run_pipeline(
                pipeline=pipeline,
                product_source=product_source,
                source_name=source_name,
            )

            # ------------------------------------------------
            # Result
            # ------------------------------------------------

            new_normalized_name = (
                pipeline_result.get(
                    "core_name"
                )
                or ""
            ).strip()

            # ------------------------------------------------
            # Empty result protection
            # ------------------------------------------------

            if not new_normalized_name:
                result.empty += 1

                print(
                    "\n[EMPTY RESULT]"
                    f" ID={product_source.id}"
                    f" SOURCE={source_code}"
                )

                print(
                    "  SOURCE NAME :",
                    source_name,
                )

                print(
                    "  OLD NORMAL :",
                    old_normalized_name or None,
                )

                return

            # ------------------------------------------------
            # Unchanged
            # ------------------------------------------------

            if (
                old_normalized_name
                == new_normalized_name
            ):
                result.unchanged += 1
                return

            # ------------------------------------------------
            # Changed
            # ------------------------------------------------

            result.changed += 1

            if self.print_changes:
                self._print_change(
                    product_source=product_source,
                    source_name=source_name,
                    old_normalized_name=old_normalized_name,
                    new_normalized_name=new_normalized_name,
                    pipeline_result=pipeline_result,
                )

            # ------------------------------------------------
            # Save
            # ------------------------------------------------

            if self.save:
                self._save(
                    product_source=product_source,
                    normalized_name=new_normalized_name,
                )

        except Exception as exc:
            result.failed += 1

            failed_row = {
                "id": product_source.id,
                "source": source_code,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

            result.failed_rows.append(
                failed_row
            )

            print(
                "\n[FAILED]"
                f" ID={product_source.id}"
                f" SOURCE={source_code}"
            )

            print(
                "  ERROR:",
                failed_row["error_type"],
                "|",
                failed_row["error"],
            )

    # ========================================================
    # Pipeline adapter
        # ========================================================
    @staticmethod
    def _run_pipeline(
        *,
        pipeline: ProductNormalizationPipeline,
        product_source: ProductSource,
        source_name: str,
    ) -> dict:
        """
        STEP02 V2 Pipeline 실행.

        ProductNormalizationPipeline은 ProductSource를 입력받고
        내부 Adapter에서 source_name을 읽는다.

        source_name 인자는 runner의 입력 검증 및 출력용으로 유지한다.
        실제 normalization 입력은 ProductSource.source_name이다.
        """

        if not source_name:
            raise ValueError(
                f"source_name이 비어 있습니다. "
                f"ProductSource ID={product_source.id}"
            )

        return pipeline.run(
            product_source
        )
    # ========================================================
    # Save
    # ========================================================

    @staticmethod
    def _save(
        *,
        product_source: ProductSource,
        normalized_name: str,
    ) -> None:
        """
        source_name은 건드리지 않고
        normalized_name만 갱신한다.
        """

        ProductSource.objects.filter(
            id=product_source.id,
        ).update(
            normalized_name=normalized_name,
        )

        # 현재 객체도 최신 상태로 맞춘다.
        product_source.normalized_name = (
            normalized_name
        )

    # ========================================================
    # Change output
    # ========================================================

    def _print_change(
        self,
        *,
        product_source: ProductSource,
        source_name: str,
        old_normalized_name: str,
        new_normalized_name: str,
        pipeline_result: dict,
    ) -> None:

        print(
            "\n"
            + "-" * 100
        )

        print(
            "[CHANGE]"
            f" ID={product_source.id}"
            f" SOURCE={product_source.source.code}"
        )

        print(
            "SOURCE NAME :",
            source_name,
        )

        print(
            "OLD NORMAL  :",
            old_normalized_name or None,
        )

        print(
            "NEW NORMAL  :",
            new_normalized_name,
        )

        if not self.print_removed:
            return

        noise_decisions = (
            pipeline_result.get(
                "noise_decisions",
                [],
            )
            or []
        )

        removed = [
            decision
            for decision in noise_decisions
            if decision.get("action")
            == "REMOVE"
        ]

        if not removed:
            return

        print("REMOVED     :")

        for decision in removed:
            print(
                "  -",
                repr(
                    decision.get("text")
                ),
                "|",
                decision.get("reason"),
            )

    # ========================================================
    # Header
    # ========================================================

    def _print_header(
        self,
        *,
        brand: Brand,
        total: int,
    ) -> None:

        print("\n")
        print("=" * 100)
        print(
            "BRAND PRODUCT NORMALIZATION V2"
        )
        print("=" * 100)

        print(
            "BRAND ID      :",
            brand.id,
        )

        print(
            "BRAND         :",
            str(brand),
        )

        print(
            "PRODUCTSOURCE :",
            f"{total:,}",
        )

        print(
            "SAVE          :",
            self.save,
        )

        print(
            "INPUT         :",
            "source_name",
        )

        print(
            "COMPARE       :",
            "기존 normalized_name",
        )

        print(
            "OUTPUT        :",
            "normalized_name",
        )

        print("=" * 100)

    # ========================================================
    # Progress
    # ========================================================

    @staticmethod
    def _print_progress(
        *,
        result: BrandNormalizationResult,
        started_at: float,
    ) -> None:

        elapsed = (
            time.perf_counter()
            - started_at
        )

        speed = (
            result.processed / elapsed
            if elapsed > 0
            else 0
        )

        percent = (
            result.processed
            / result.total
            * 100
            if result.total
            else 100
        )

        remaining = (
            result.total
            - result.processed
        )

        eta_seconds = (
            remaining / speed
            if speed > 0
            else 0
        )

        print(
            "\n"
            f"[{result.processed:,}/{result.total:,}] "
            f"{percent:6.2f}%"
            f" | 변경 {result.changed:,}"
            f" | 동일 {result.unchanged:,}"
            f" | EMPTY {result.empty:,}"
            f" | 실패 {result.failed:,}"
            f" | {speed:.1f}개/s"
            f" | ETA {eta_seconds:.1f}s"
        )

    # ========================================================
    # Summary
    # ========================================================

    @staticmethod
    def _print_summary(
        *,
        result: BrandNormalizationResult,
    ) -> None:

        print("\n")
        print("=" * 100)
        print(
            "NORMALIZATION COMPLETE"
        )
        print("=" * 100)

        print(
            "BRAND      :",
            f"{result.brand_name}"
            f" (ID={result.brand_id})",
        )

        print(
            "전체       :",
            f"{result.total:,}",
        )

        print(
            "처리       :",
            f"{result.processed:,}",
        )

        print(
            "변경       :",
            f"{result.changed:,}",
        )

        print(
            "동일       :",
            f"{result.unchanged:,}",
        )

        print(
            "EMPTY      :",
            f"{result.empty:,}",
        )

        print(
            "실패       :",
            f"{result.failed:,}",
        )

        print(
            "소요시간   :",
            f"{result.elapsed_seconds:.2f}초",
        )

        if result.failed_rows:
            print(
                "\n[FAILED ROWS]"
            )

            for row in result.failed_rows[:100]:
                print(
                    row["id"],
                    "|",
                    row["source"],
                    "|",
                    row["error_type"],
                    "|",
                    row["error"],
                )

            remaining_failed = (
                len(result.failed_rows)
                - 100
            )

            if remaining_failed > 0:
                print(
                    "... 외",
                    f"{remaining_failed:,}",
                    "건",
                )

        print("=" * 100)


# ============================================================
# Shell shortcut
# ============================================================


def normalize_brand_products(
    brand_id: int,
    *,
    save: bool = False,
    print_changes: bool = True,
    print_removed: bool = True,
    print_every: int = 50,
) -> BrandNormalizationResult:
    """
    특정 브랜드의 모든 ProductSource를
    source_name부터 STEP02 V2로 다시 정규화한다.

    Dry run
    -------
    normalize_brand_products(
        3069,
        save=False,
    )

    Save
    ----
    normalize_brand_products(
        3069,
        save=True,
    )
    """

    runner = BrandProductNormalizationRunner(
        save=save,
        print_changes=print_changes,
        print_removed=print_removed,
        print_every=print_every,
    )

    return runner.run(
        brand_id=brand_id,
    )