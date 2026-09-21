from __future__ import annotations

from collections import OrderedDict
from typing import Any


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _market_payload(market: dict[str, Any]) -> dict[str, Any]:
    values = {
        "market_sno": _clean(market.get("market_sno")),
        "market_name": _clean(market.get("market_name")),
        "market_type": _clean(market.get("market_type")),
        "market_type_sno": _clean(market.get("market_type_sno")),
    }
    return {key: value for key, value in values.items() if value is not None}


def _market_key(market: dict[str, Any]) -> str | None:
    market_sno = market.get("market_sno")
    if market_sno:
        return f"ID:{market_sno}"
    market_name = market.get("market_name")
    if market_name:
        return f"NAME:{market_name.casefold()}"
    return None


def build_brand_source_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Build one ABLY BrandSource candidate per brand or market fallback."""

    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for category in payload.get("categories") or []:
        if not isinstance(category, dict):
            continue
        for product in category.get("products") or []:
            if not isinstance(product, dict):
                continue

            brand = product.get("brand") if isinstance(product.get("brand"), dict) else {}
            market = product.get("market") if isinstance(product.get("market"), dict) else {}
            brand_sno = _clean(brand.get("brand_sno"))
            brand_name = _clean(brand.get("brand_name"))
            market_data = _market_payload(market)
            market_sno = market_data.get("market_sno")
            market_name = market_data.get("market_name")

            if brand_name:
                source_brand_id = brand_sno or f"NAME:{brand_name}"
                candidate_kind = "BRAND"
                name = brand_name
            elif market_sno or market_name:
                source_brand_id = (
                    f"MARKET:{market_sno}"
                    if market_sno
                    else f"MARKET_NAME:{market_name}"
                )
                candidate_kind = "MARKET_FALLBACK"
                name = market_name
            else:
                continue

            candidate = grouped.setdefault(
                source_brand_id,
                {
                    "source_brand_id": source_brand_id,
                    "name": name,
                    "candidate_kind": candidate_kind,
                    "markets": OrderedDict(),
                    "observed_brand_snos": [],
                    "appearance_count": 0,
                },
            )
            if not candidate["name"] and name:
                candidate["name"] = name
            candidate["appearance_count"] += 1

            market_key = _market_key(market_data)
            if market_key:
                existing = candidate["markets"].get(market_key, {})
                candidate["markets"][market_key] = {**existing, **market_data}

            if candidate_kind == "MARKET_FALLBACK" and brand_sno:
                if brand_sno not in candidate["observed_brand_snos"]:
                    candidate["observed_brand_snos"].append(brand_sno)

    results = []
    for candidate in grouped.values():
        attributes = {
            "candidate_kind": candidate["candidate_kind"],
            "markets": list(candidate["markets"].values()),
        }
        if candidate["observed_brand_snos"]:
            attributes["observed_brand_snos"] = candidate["observed_brand_snos"]
        attributes["appearance_count"] = candidate["appearance_count"]
        results.append(
            {
                "source_brand_id": candidate["source_brand_id"],
                "name": candidate["name"],
                "attributes": attributes,
            }
        )
    return results


def choose_brand_source_name(existing: Any, incoming: Any) -> tuple[Any, bool]:
    """Fill only a blank existing name and report whether it changed."""

    if _clean(existing) is not None:
        return existing, False
    cleaned_incoming = _clean(incoming)
    if cleaned_incoming is None:
        return existing, False
    return cleaned_incoming, True


def merge_brand_source_attributes(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Merge market lists without discarding unrelated existing attributes."""

    merged = dict(existing or {})
    old_markets = merged.get("markets") if isinstance(merged.get("markets"), list) else []
    markets: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for market in [*old_markets, *(incoming.get("markets") or [])]:
        if not isinstance(market, dict):
            continue
        market_data = _market_payload(market)
        key = _market_key(market_data)
        if key:
            markets[key] = {**markets.get(key, {}), **market_data}

    merged.update({key: value for key, value in incoming.items() if key != "markets"})
    merged["markets"] = list(markets.values())
    return merged
