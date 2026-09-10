from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, get_ident
from urllib.parse import parse_qs, urlparse

from .client import MusinsaUsedClient
from .constants import (
    DEFAULT_RANKING_LIMIT,
    PRODUCT_BASE_URL,
    RANKING_API_URL,
    USED_RELATED_GOODS_API_URL,
    USED_SALE_INFORMATION_API_URL,
)
from .parser import MusinsaUsedParser


class MusinsaUsedCollector:
    """Collect one MUSINSA USED ranking or product without S3 concerns."""

    def __init__(
        self,
        *,
        timeout: int | float | None = None,
        session=None,
        product_client_factory=MusinsaUsedClient,
    ):
        self.client = MusinsaUsedClient(
            timeout=timeout,
            session=session,
        )
        self._product_client_factory = product_client_factory
        self._product_clients: dict[int, MusinsaUsedClient] = {}
        self._product_clients_lock = Lock()

    def close(self) -> None:
        self.client.close()
        with self._product_clients_lock:
            product_clients = list(self._product_clients.values())
            self._product_clients.clear()
        for product_client in product_clients:
            product_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # Manual browser-capture inputs remain supported for reproducibility.
    def collect_ranking(
        self,
        html_path: str | Path,
        *,
        limit: int | None = DEFAULT_RANKING_LIMIT,
        source_url: str | None = None,
    ) -> dict:
        items = MusinsaUsedParser.parse_ranking(
            self.client.read_html(html_path), limit=limit
        )
        return {
            "source_url": source_url,
            "source_file": str(html_path),
            "collected_at": self._now(),
            "items": items,
        }

    def collect_ranking_live(
        self,
        target_url: str,
        *,
        limit: int = DEFAULT_RANKING_LIMIT,
    ) -> dict:
        scope = self.ranking_scope(target_url)
        body = self.client.get_json(
            RANKING_API_URL,
            params={
                "storeCode": scope["store_code"],
                "sectionId": scope["section_id"],
                "contentsId": scope["contents_id"],
                "subPan": scope["sub_pan"],
                "gf": scope["gender"],
                "categoryCode": scope["category_code"],
                "ageBand": scope["age_band"],
                "period": scope["period"],
            },
            referer=target_url,
        )
        return {
            "source_url": target_url,
            "collected_at": self._now(),
            "items": MusinsaUsedParser.parse_ranking_response(
                body,
                ranking_scope=scope,
                limit=limit,
            ),
        }

    def collect_product_record_from_html(
        self,
        html_path: str | Path,
        *,
        goods_no: str | int,
        sale_information_path: str | Path | None = None,
        related_goods_path: str | Path | None = None,
        ranking_context: dict | None = None,
        source_url: str | None = None,
    ) -> dict:
        sale_information = (
            self.client.read_json(sale_information_path)
            if sale_information_path
            else None
        )
        related_goods = (
            self.client.read_json(related_goods_path) if related_goods_path else None
        )
        return MusinsaUsedParser.parse_product_record_from_html(
            self.client.read_html(html_path),
            goods_no=goods_no,
            sale_information=sale_information,
            related_goods=related_goods,
            ranking_context=ranking_context,
            meta={
                "request_url": source_url or PRODUCT_BASE_URL.format(goods_no=goods_no),
                "source_file": str(html_path),
            },
        )

    def collect_product_live(
        self,
        goods_no: str | int,
        *,
        ranking_context: dict | None = None,
    ) -> dict:
        product_url = PRODUCT_BASE_URL.format(goods_no=goods_no)
        product_client = self._get_product_client()
        metric_start = len(product_client.request_metrics)
        response = product_client.get_html(product_url)
        enrichment_urls = {
            "sale_information": USED_SALE_INFORMATION_API_URL.format(goods_no=goods_no),
            "related_goods": USED_RELATED_GOODS_API_URL.format(goods_no=goods_no),
        }
        enrichments: dict[str, dict | None] = {}
        enrichment_errors: list[dict] = []
        for name, url in enrichment_urls.items():
            try:
                enrichments[name] = product_client.get_json(url, referer=product_url)
            except Exception as exc:
                enrichments[name] = None
                enrichment_errors.append(
                    {
                        "enrichment": name,
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    }
                )

        sale_information = enrichments.get("sale_information")
        related_goods = enrichments.get("related_goods")
        # Options describe all available sizes, not this USED listing's size.
        # They are deliberately excluded from the default live request path.
        options = {}

        return MusinsaUsedParser.parse_product_record_from_html(
            response.text,
            goods_no=goods_no,
            sale_information=sale_information,
            related_goods=related_goods,
            options=options,
            ranking_context=ranking_context,
            meta={
                "request_url": product_url,
                "final_url": getattr(response, "url", product_url),
                "http_status": getattr(response, "status_code", None),
                "content_type": getattr(response, "headers", {}).get("Content-Type"),
                "request_metrics": product_client.request_metrics[metric_start:],
                "enrichment_errors": enrichment_errors,
            },
        )

    @staticmethod
    def ranking_scope(target_url: str) -> dict:
        query = parse_qs(urlparse(target_url).query, keep_blank_values=True)

        def get(key: str, default=None):
            values = query.get(key)
            return values[0] if values else default

        return {
            "store_code": get("storeCode", "used"),
            "section_id": get("sectionId", "200"),
            "contents_id": get("contentsId", ""),
            "category_code": get("categoryCode", get("category", "109")),
            "gender": get("gf", "A"),
            "age_band": get("ageBand", "AGE_BAND_ALL"),
            "sub_pan": get("subPan", "product"),
            "period": get("period", "DAILY"),
            "ranking_type": get("sortCode", "VIEW_ONE_DAY_DIFF"),
        }

    def _get_product_client(self) -> MusinsaUsedClient:
        thread_id = get_ident()
        with self._product_clients_lock:
            client = self._product_clients.get(thread_id)
            if client is None:
                client = self._product_client_factory(
                    timeout=self.client.timeout,
                    backoff_coordinator=self.client.backoff_coordinator,
                    request_limiter=self.client.request_limiter,
                )
                self._product_clients[thread_id] = client
            return client

    def aggregate_request_metrics(self) -> list[dict]:
        """Return independent client metrics as one per-Target collection view."""
        with self._product_clients_lock:
            product_clients = list(self._product_clients.values())
        return [
            *self.client.request_metrics,
            *(metric for client in product_clients for metric in client.request_metrics),
        ]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
