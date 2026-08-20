import hashlib
import json
from typing import Any

from django.utils import timezone

from apps.naver.models import NaverApiRequest


def _request_hash(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def was_collected_today(source: str, payload: Any) -> bool:
    return NaverApiRequest.objects.filter(
        source=source,
        request_hash=_request_hash(payload),
        collection_date=timezone.localdate(),
    ).exists()


def mark_collected_today(source: str, payload: Any) -> None:
    NaverApiRequest.objects.get_or_create(
        source=source,
        request_hash=_request_hash(payload),
        collection_date=timezone.localdate(),
    )
