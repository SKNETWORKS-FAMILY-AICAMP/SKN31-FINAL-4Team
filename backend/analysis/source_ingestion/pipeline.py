from __future__ import annotations

from typing import Any

from .musinsa import MusinsaNormalizer
from .zigzag import ZigzagNormalizer
from .ably import AblyNormalizer

class SourceIngestionPipeline:
    """
    FEEDIT SOURCE INGESTION 단일 진입점.

    책임
    ----
    플랫폼별 raw/parser 결과를 기존 normalizer에 전달해
    Source 레이어를 생성/갱신한다.

    현재 지원
    ---------
    MUSINSA
        parser output
        -> BrandSource
        -> CategorySource
        -> ProductSource

    ZIGZAG
        raw / pipeline payload
        -> BrandSource
        -> CategorySource
        -> ProductSource
        -> ProductSourceSnapshot

    원칙
    ----
    - 플랫폼별 세부 정규화 규칙은 여기서 구현하지 않는다.
    - 기존 MusinsaNormalizer / ZigzagNormalizer를 그대로 호출한다.
    - Product / ProductAttribute / DictionaryTerm 처리는 하지 않는다.
    - Product enrichment와 term discovery는 별도 단계다.
    """

    SUPPORTED_SOURCES = {
        "MUSINSA",
        "ZIGZAG",
        "ABLY",
    }

    def __init__(self, *, source):
        self.source = source
        self.source_code = self._source_code(source)

        if self.source_code not in self.SUPPORTED_SOURCES:
            raise ValueError(
                "지원하지 않는 source입니다: "
                f"{self.source_code or '<EMPTY>'}. "
                f"supported={sorted(self.SUPPORTED_SOURCES)}"
            )

    # ============================================================
    # PUBLIC
    # ============================================================

    def run(
        self,
        payload: dict[str, Any],
        *,
        create_snapshot: bool = True,
    ) -> dict[str, Any]:
        """
        SOURCE INGESTION 실행.

        Parameters
        ----------
        payload:
            MUSINSA: Musinsa parser 결과 dict
            ZIGZAG : S3 raw JSON 또는 pipeline payload dict

        create_snapshot:
            MUSINSA / ZIGZAG ProductSourceSnapshot 생성 여부.
        """

        if not isinstance(payload, dict):
            raise ValueError("payload는 dict여야 합니다.")

        if self.source_code == "MUSINSA":
            return self._run_musinsa(
                payload,
                create_snapshot=create_snapshot,
            )

        if self.source_code == "ZIGZAG":
            return self._run_zigzag(
                payload,
                create_snapshot=create_snapshot,
            )

        # __init__에서 이미 차단하지만 방어적으로 남긴다.
        raise ValueError(
            f"지원하지 않는 source입니다: {self.source_code}"
        )

    # ============================================================
    # MUSINSA
    # ============================================================

    def _run_musinsa(
        self,
        payload: dict[str, Any],
        *,
        create_snapshot: bool,
    ) -> dict[str, Any]:
        normalizer = MusinsaNormalizer(
            source=self.source,
        )

        result = normalizer.normalize_product_source(
            payload
        )

        product_source = result.get("product_source")
        brand_result = result.get("brand_result") or {}
        category_result = result.get("category_result") or {}

        snapshot_result = {
            "created": False,
            "snapshot": None,
            "observed_at": None,
        }

        if create_snapshot and product_source is not None:
            snapshot_result = normalizer.normalize_snapshot(
                payload,
                product_source=product_source,
            )

        return {
            "source": self.source_code,
            "ok": True,
            "product_source": product_source,
            "product_source_id": getattr(
                product_source,
                "id",
                None,
            ),
            "source_product_id": getattr(
                product_source,
                "source_product_id",
                None,
            ),
            "created": bool(result.get("created")),
            "brand_source": result.get("source_brand"),
            "brand_source_created": brand_result.get("created"),
            "brand_matched": brand_result.get("matched"),
            "category_source": result.get("source_category"),
            "category_source_created": category_result.get("created"),
            "category_matched": category_result.get("matched"),
            "snapshot": snapshot_result.get("snapshot"),
            "snapshot_created": bool(snapshot_result.get("created")),
            "observed_at": snapshot_result.get("observed_at"),
            "snapshot_supported": True,
            "raw_result": result,
        }

    # ============================================================
    # ZIGZAG
    # ============================================================

    def _run_zigzag(
        self,
        payload: dict[str, Any],
        *,
        create_snapshot: bool,
    ) -> dict[str, Any]:
        normalizer = ZigzagNormalizer(
            source=self.source,
        )

        result = normalizer.normalize_ranking_payload(
            payload,
            create_snapshot=create_snapshot,
        )

        return {
            "source": self.source_code,
            "ok": len(result.get("errors") or []) == 0,
            "count": result.get("count", 0),
            "observed_at": result.get("observed_at"),
            "brand_sources": result.get("brand_sources") or {},
            "category_sources": result.get("category_sources") or {},
            "product_sources": result.get("product_sources") or {},
            "snapshots": result.get("snapshots") or {},
            "snapshot_supported": True,
            "errors": result.get("errors") or [],
            "items": result.get("items") or [],
            "raw_result": result,
        }

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _source_code(source) -> str:
        return str(
            getattr(source, "code", "") or ""
        ).strip().upper()
