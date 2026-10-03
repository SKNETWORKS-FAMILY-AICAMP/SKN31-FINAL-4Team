from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import (
    AnalysisPipelineRun,
    ContentItem,
    DictionaryTerm,
    ProductReview,
    TermAlias,
    TextDocument,
    TextTermMention,
)

from .evidence import resolve_evidence
from .llm import LLMUsage, OpenAITextSignalClient
from .metrics import rebuild_text_metrics
from .prompts import PROMPT_VERSION


PIPELINE_VERSION = "feedit-text-signals-v2"
BATCH_SIZE = int(os.getenv("FEEDIT_TEXT_BATCH_SIZE", "24"))
PREFILTER_SIGNAL = re.compile(
    r"\?|까요|나요|어디|얼마|추천|궁금|사이즈|재질|소재|핏|색|"
    r"사야|살까|샀|구매|주문|장바구니|재입고|품절|"
    r"좋|예쁘|이쁘|별로|아쉽|실망|불편|비싸|싫|최악|보풀|환불|반품"
)
SLOT_BY_TYPE = {
    "STYLE": "style",
    "ITEM": "item",
    "MATERIAL": "material",
    "DETAIL": "detail",
    "COLOR": "color",
    "TPO": "tpo",
}
POLARITY_SCORE = {"POS": Decimal("1"), "NEU": Decimal("0.5"), "NEG": Decimal("0")}
TOKEN_PRICES_PER_MILLION = {
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-6-luna": (0.10, 0.01, 0.50),
}


def _norm(value: str | None) -> str:
    return re.sub(r"[\s\-_/()]+", "", str(value or "")).lower()


class DictionaryIndex:
    def __init__(self):
        self.by_surface: dict[str, dict] = {}
        self.by_first: dict[str, set[str]] = defaultdict(set)
        self.terms_by_type: dict[str, list[str]] = defaultdict(list)

        terms = list(DictionaryTerm.objects.filter(status="ACTIVE").values(
            "id", "term_type", "canonical_name", "normalized_name", "english_name"
        ))
        for row in terms:
            self.terms_by_type[row["term_type"]].append(row["canonical_name"])
            for value in (row["canonical_name"], row["normalized_name"], row["english_name"]):
                self._add(value, row)
        for alias in TermAlias.objects.select_related("term").filter(term__status="ACTIVE").values(
            "alias", "normalized_alias", "term_id", "term__term_type", "term__canonical_name"
        ):
            row = {
                "id": alias["term_id"],
                "term_type": alias["term__term_type"],
                "canonical_name": alias["term__canonical_name"],
            }
            self._add(alias["alias"], row)
            self._add(alias["normalized_alias"], row)

    def _add(self, surface, row):
        key = _norm(surface)
        if len(key) < 2:
            return
        self.by_surface.setdefault(key, row)
        self.by_first[key[0]].add(key)

    def find(self, *values):
        for value in values:
            hit = self.by_surface.get(_norm(value))
            if hit:
                return hit
        return None

    def contains(self, text: str) -> bool:
        normalized = _norm(text)
        for index, char in enumerate(normalized):
            for surface in self.by_first.get(char, ()):
                if normalized.startswith(surface, index):
                    return True
        return False

    def prompt_text(self) -> str:
        labels = [
            ("STYLE", "스타일"), ("ITEM", "아이템"), ("MATERIAL", "소재"),
            ("DETAIL", "디테일·핏"), ("COLOR", "색상"), ("TPO", "상황"),
        ]
        return "\n".join(
            f"{label}: {', '.join(sorted(set(self.terms_by_type.get(term_type, []))))}"
            for term_type, label in labels
        )


def _safe_meta(value) -> dict:
    return value if isinstance(value, dict) else {}


def _published(value):
    if value is None:
        return None
    return value


@transaction.atomic
def sync_product_reviews(*, limit: int | None = None) -> dict:
    """commerce.product_review 원문을 분석용 TextDocument로 손실 없이 동기화한다."""

    query = ProductReview.objects.select_related("product_source__source").order_by("id")
    if limit:
        query = query[:limit]
    reviews = list(query)
    keys_by_source: dict[int, list[str]] = defaultdict(list)
    for review in reviews:
        keys_by_source[review.product_source.source_id].append(str(review.source_review_id))
    existing = {}
    for source_id, keys in keys_by_source.items():
        for doc in TextDocument.objects.filter(
            source_id=source_id,
            document_type=TextDocument.DocumentType.REVIEW,
            external_id__in=keys,
        ):
            existing[(source_id, doc.external_id)] = doc

    created = updated = unchanged = 0
    to_create: list[TextDocument] = []
    for review in reviews:
        source_id = review.product_source.source_id
        external_id = str(review.source_review_id)[:255]
        body = str(review.content or "").strip()
        if not body:
            continue
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        metadata = {
            "origin": "commerce.product_review",
            "review_id": review.id,
            "review_type": review.review_type,
            "grade": review.grade,
            "goods_option": review.goods_option,
            "like_count": review.like_count,
            "reviewer_sex": review.reviewer_sex,
            "reviewer_height": review.reviewer_height,
            "reviewer_weight": review.reviewer_weight,
            "survey": review.survey if isinstance(review.survey, dict) else {},
        }
        document = existing.get((source_id, external_id))
        if document is None:
            to_create.append(TextDocument(
                source_id=source_id,
                product_source_id=review.product_source_id,
                document_type=TextDocument.DocumentType.REVIEW,
                external_id=external_id,
                body=body,
                language="ko",
                source_published_at=_published(review.source_created_at or review.created_at),
                source_payload_hash=payload_hash,
                analysis_metadata=metadata,
                analysis_status=TextDocument.AnalysisStatus.PENDING,
            ))
            created += 1
            continue

        body_changed = document.source_payload_hash != payload_hash or document.body != body
        merged_metadata = {**_safe_meta(document.analysis_metadata), **metadata}
        if not body_changed:
            metadata_changed = (
                document.product_source_id != review.product_source_id
                or document.source_published_at != _published(review.source_created_at or review.created_at)
                or document.analysis_metadata != merged_metadata
            )
            if metadata_changed:
                document.product_source_id = review.product_source_id
                document.source_published_at = _published(review.source_created_at or review.created_at)
                document.analysis_metadata = merged_metadata
                document.save(update_fields=[
                    "product_source", "source_published_at", "analysis_metadata", "updated_at",
                ])
                updated += 1
            else:
                unchanged += 1
            continue
        document.product_source_id = review.product_source_id
        document.body = body
        document.source_published_at = _published(review.source_created_at or review.created_at)
        document.source_payload_hash = payload_hash
        document.analysis_status = TextDocument.AnalysisStatus.PENDING
        document.analysis_version = ""
        document.analysis_metadata = merged_metadata
        document.save(update_fields=[
            "product_source", "body", "source_published_at", "source_payload_hash",
            "analysis_status", "analysis_version", "analysis_metadata", "updated_at",
        ])
        updated += 1
    if to_create:
        TextDocument.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)
    return {"created": created, "updated": updated, "unchanged": unchanged}


# ★ 2026-09-20 — 콘텐츠 본문(영상 제목 + 설명)도 분석 대상 문서로 만든다.
#   댓글만 분석하면 '고프코어' 같은 스타일 용어가 거의 잡히지 않는다. 크리에이터가 영상 제목·설명에
#   쓰는 말이 트렌드의 본체다. 자막(TRANSCRIPT) · 기사(ARTICLE) 문서가 들어오면 같은 흐름을 탄다.
CONTENT_DOC_TYPES = ("DESCRIPTION", "TRANSCRIPT", "ARTICLE")
ANALYZED_DOC_TYPES = ("COMMENT", "REVIEW", *CONTENT_DOC_TYPES)
CONTENT_BODY_MAX = 6000


def _content_body(item) -> str:
    title = str(item.title or "").strip()
    desc = str(item.description or "").strip()
    return (title + ("\n\n" + desc if desc else "")).strip()[:CONTENT_BODY_MAX]


def sync_content_documents(*, limit: int | None = None) -> dict:
    """content.content_item(영상 등) → text_document(DESCRIPTION) 한 건씩.

    · 본문 = 제목 + 설명. 바뀌었으면 다시 분석 대기(PENDING)로 돌린다.
    · 작성일(source_published_at) = 콘텐츠 게시 시각 — 예전에 만든 설명 문서는 이 값이 비어
      지표에서 통째로 빠졌다(2026-09-20 실측 968건 전부).
    """
    items = ContentItem.objects.exclude(published_at__isnull=True).order_by("id")
    if limit:
        items = items[:limit]
    items = list(items.only("id", "source_id", "title", "description", "published_at",
                            "external_content_id"))
    existing = {d.content_item_id: d for d in TextDocument.objects.filter(
        document_type=TextDocument.DocumentType.DESCRIPTION,
        content_item_id__in=[i.id for i in items])}
    created = updated = unchanged = dated = 0
    to_create: list[TextDocument] = []
    for item in items:
        body = _content_body(item)
        if not body:
            continue
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        published = _published(item.published_at)
        doc = existing.get(item.id)
        if doc is None:
            to_create.append(TextDocument(
                source_id=item.source_id, content_item_id=item.id,
                document_type=TextDocument.DocumentType.DESCRIPTION,
                # 기존 설명 문서와 같은 모양: "<영상 ID>:description"
                external_id=f"{item.external_content_id or item.id}:description"[:255],
                body=body, language="ko",
                source_published_at=published, source_payload_hash=payload_hash,
                analysis_metadata={"origin": "content.content_item", "content_item_id": item.id},
                analysis_status=TextDocument.AnalysisStatus.PENDING,
            ))
            created += 1
            continue
        if doc.body != body:
            doc.body = body
            doc.source_payload_hash = payload_hash
            doc.source_published_at = published
            doc.analysis_status = TextDocument.AnalysisStatus.PENDING
            doc.analysis_version = ""
            doc.save(update_fields=["body", "source_payload_hash", "source_published_at",
                                    "analysis_status", "analysis_version", "updated_at"])
            updated += 1
        elif doc.source_published_at != published:
            doc.source_published_at = published
            doc.save(update_fields=["source_published_at", "updated_at"])
            dated += 1
        else:
            unchanged += 1
    if to_create:
        TextDocument.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)
    return {"created": created, "updated": updated, "dated": dated, "unchanged": unchanged}


def _iter_tag_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_tag_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_tag_values(item)


def _attributed(document: TextDocument, slot: str, canonical: str) -> bool:
    if not document.content_item_id:
        return False
    tags = _safe_meta(document.content_item.analysis_tags)
    values = {_norm(value) for value in _iter_tag_values(tags.get(slot) or [])}
    return _norm(canonical) in values


def _llm_input(document: TextDocument) -> dict:
    context = {}
    if document.content_item_id and document.document_type in CONTENT_DOC_TYPES:
        context = {
            "kind": "creator_content",   # 영상 제목·설명 · 자막 — 크리에이터가 쓴 본문
            "document_type": document.document_type,
            "analysis_tags": document.content_item.analysis_tags,
        }
        return {"id": document.id, "body": document.body[:3200], "context": context}
    if document.content_item_id:
        context = {
            "kind": "youtube_comment",
            "title": document.content_item.title,
            "analysis_tags": document.content_item.analysis_tags,
        }
    elif document.product_source_id:
        product = document.product_source
        context = {
            "kind": "commerce_review",
            "product_name": product.source_name,
            "brand": product.source_brand.name if product.source_brand_id else None,
            "category": product.source_category.source_category_name if product.source_category_id else None,
            "grade": _safe_meta(document.analysis_metadata).get("grade"),
        }
    return {"id": document.id, "body": document.body[:1600], "context": context}


def _sentiment(mentions: list[dict]) -> float | None:
    if not mentions:
        return None
    total = sum(POLARITY_SCORE.get(item["polarity"], Decimal("0.5")) for item in mentions)
    return float((total / Decimal(len(mentions))).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP))


def _should_keep(target: str, intent: str, mentions: list[dict], candidates: list[dict]) -> bool:
    if mentions or candidates:
        return True
    return target == "PRODUCT" and intent in {"QUESTION", "PURCHASE", "CRITIQUE", "EXPERIENCE"}


def _validated_result(document: TextDocument, raw: dict, dictionary: DictionaryIndex) -> tuple[list, list, list, dict]:
    mentions: list[dict] = []
    mention_objects: list[TextTermMention] = []
    candidates: list[dict] = []
    errors: list[dict] = []
    role = (TextTermMention.MentionRole.REVIEW if document.document_type == TextDocument.DocumentType.REVIEW
            else TextTermMention.MentionRole.TARGET if document.document_type in CONTENT_DOC_TYPES
            else TextTermMention.MentionRole.COMMENT)

    merged: dict[int, tuple[dict, TextTermMention]] = {}
    for item in raw.get("mentions") or []:
        hit = dictionary.find(item.get("term"), item.get("surface"))
        if not hit or hit.get("term_type") not in SLOT_BY_TYPE:
            candidates.append({
                "term": item.get("term"), "guess": str(item.get("slot") or "UNKNOWN").upper(),
                "surface": item.get("surface"), "span": item.get("evidence_quote"),
                "polarity": item.get("polarity") or "NEU",
            })
            continue
        evidence = resolve_evidence(
            document.body,
            quote=item.get("evidence_quote") or "",
            surface=item.get("surface") or "",
            start=item.get("char_start"),
            end=item.get("char_end"),
        )
        if not evidence.valid:
            errors.append({"term": item.get("term"), "surface": item.get("surface"), "reason": evidence.reason})
            continue
        slot = SLOT_BY_TYPE[hit["term_type"]]
        polarity = item.get("polarity") if item.get("polarity") in POLARITY_SCORE else "NEU"
        confidence = max(0.0, min(1.0, float(item.get("confidence") or 0)))
        attributed = _attributed(document, slot, hit["canonical_name"])
        meta = {
            "facet": slot, "source": "text_signal_pipeline", "match_type": "dictionary",
            "original_value": item.get("surface"), "target": raw.get("target") or "OTHER",
            "attributed": attributed,
        }
        normalized = {
            "term": hit["canonical_name"], "slot": slot, "span": evidence.quote,
            "char_start": evidence.start, "char_end": evidence.end,
            "evidence_status": evidence.status, "polarity": polarity,
            "confidence": confidence, "attributed": attributed,
        }
        obj = TextTermMention(
            document=document,
            term_id=hit["id"],
            mention_text=evidence.quote,
            mention_role=role,
            sentiment_score=POLARITY_SCORE[polarity],
            intent_code=raw.get("intent"),
            confidence=Decimal(str(round(confidence, 5))),
            evidence_start=evidence.start,
            evidence_end=evidence.end,
            evidence_status=evidence.status,
            analysis_version=PIPELINE_VERSION,
            analysis_metadata=meta,
        )
        previous = merged.get(hit["id"])
        if previous is None or (polarity == "NEG" and previous[0]["polarity"] != "NEG"):
            merged[hit["id"]] = (normalized, obj)

    for item in raw.get("candidates") or []:
        evidence = resolve_evidence(
            document.body,
            quote=item.get("evidence_quote") or "",
            surface=item.get("surface") or item.get("term") or "",
            start=item.get("char_start"),
            end=item.get("char_end"),
        )
        if evidence.valid:
            candidates.append({
                "term": item.get("term"), "guess": item.get("guess") or "UNKNOWN",
                "surface": item.get("surface"), "span": evidence.quote,
                "char_start": evidence.start, "char_end": evidence.end,
                "evidence_status": evidence.status, "polarity": item.get("polarity") or "NEU",
            })

    for normalized, obj in merged.values():
        mentions.append(normalized)
        mention_objects.append(obj)
    return mentions, candidates, errors, {"objects": mention_objects, "role": role}


def _save_prefiltered(document: TextDocument, run: AnalysisPipelineRun) -> None:
    meta = _safe_meta(document.analysis_metadata)
    meta.update({
        "intent": "CHITCHAT", "target": "OTHER", "keep": False,
        "sentiment": None, "mentions": [], "candidates": [],
        "analysis": {"method": "dictionary_prefilter", "pipeline_version": PIPELINE_VERSION},
    })
    document.analysis_metadata = meta
    document.analysis_status = TextDocument.AnalysisStatus.DONE
    document.analyzed_at = timezone.now()
    document.analysis_version = PIPELINE_VERSION
    document.analysis_run = run
    document.save(update_fields=[
        "analysis_metadata", "analysis_status", "analyzed_at", "analysis_version", "analysis_run", "updated_at",
    ])


def run_text_signal_pipeline(
    *,
    limit: int | None = None,
    include_stale: bool = False,
    rebuild_metrics: bool = True,
    metric_days: int = 35,
    client=None,
) -> dict:
    """1차 사전 필터 → 2차 LLM → 근거 검증 → 적재 → 일별 지표 계산."""

    model_name = os.getenv("FEEDIT_TEXT_LLM_MODEL", "gpt-6-luna")
    if model_name not in TOKEN_PRICES_PER_MILLION:
        raise ValueError(f"분석 비용 단가가 없는 모델입니다: {model_name}")
    dictionary = DictionaryIndex()
    run = AnalysisPipelineRun.objects.create(
        run_date=timezone.localdate(),
        pipeline_version=PIPELINE_VERSION,
        prompt_version=PROMPT_VERSION,
        model_name=model_name,
    )
    query = TextDocument.objects.select_related(
        "content_item", "product_source__source", "product_source__source_brand", "product_source__source_category"
    ).filter(document_type__in=list(ANALYZED_DOC_TYPES))
    if include_stale:
        query = query.filter(~Q(analysis_version=PIPELINE_VERSION) | Q(analysis_status=TextDocument.AnalysisStatus.PENDING))
    else:
        query = query.filter(analysis_status=TextDocument.AnalysisStatus.PENDING)
    query = query.order_by("id")
    if limit:
        query = query[:limit]
    documents = list(query)
    run.input_count = len(documents)
    run.save(update_fields=["input_count"])

    llm_docs: list[TextDocument] = []
    skipped = 0
    for document in documents:
        if document.document_type == TextDocument.DocumentType.REVIEW or dictionary.contains(document.body) or PREFILTER_SIGNAL.search(document.body):
            llm_docs.append(document)
        else:
            _save_prefiltered(document, run)
            skipped += 1

    llm_client = client
    usage = LLMUsage()
    analyzed = failures = 0
    validation_errors = 0
    for offset in range(0, len(llm_docs), BATCH_SIZE):
        batch = llm_docs[offset:offset + BATCH_SIZE]
        try:
            if llm_client is None:
                llm_client = OpenAITextSignalClient()
            raw_results, used = llm_client.analyze(
                [_llm_input(document) for document in batch],
                dictionary_text=dictionary.prompt_text(),
            )
            usage = LLMUsage(
                usage.input_tokens + used.input_tokens,
                usage.cached_tokens + used.cached_tokens,
                usage.output_tokens + used.output_tokens,
            )
        except Exception as exc:  # Celery 재실행을 위해 문서는 PENDING 유지
            failures += len(batch)
            run.error_message = (run.error_message + f"\n{type(exc).__name__}: {str(exc)[:300]}").strip()
            continue

        by_id = {int(item.get("id")): item for item in raw_results if item.get("id") is not None}
        for document in batch:
            raw = by_id.get(document.id)
            if raw is None:
                failures += 1
                continue
            mentions, candidates, errors, extra = _validated_result(document, raw, dictionary)
            validation_errors += len(errors)
            if (raw.get("mentions") or []) and not mentions and errors:
                # 근거가 전부 깨진 응답으로 기존 검증/레거시 언급을 지우지 않는다.
                # 문서를 PENDING에 남겨 다음 실행에서 다시 분석한다.
                failures += 1
                continue
            target = raw.get("target") or "OTHER"
            intent = raw.get("intent") or "CHITCHAT"
            keep = _should_keep(target, intent, mentions, candidates)
            meta = _safe_meta(document.analysis_metadata)
            meta.update({
                "target": target, "intent": intent, "keep": keep,
                "sentiment": _sentiment(mentions), "mentions": mentions,
                "candidates": candidates,
                "analysis": {
                    "pipeline_version": PIPELINE_VERSION,
                    "prompt_version": PROMPT_VERSION,
                    "model": run.model_name,
                    "evidence_validation_errors": errors,
                },
            })
            with transaction.atomic():
                old = TextTermMention.objects.filter(document=document)
                if document.document_type not in CONTENT_DOC_TYPES:
                    old = old.filter(mention_role=extra["role"])
                old.delete()   # 콘텐츠 본문은 예전 역할(문맥 등)로 남은 언급까지 새 결과로 바꾼다
                if extra["objects"]:
                    TextTermMention.objects.bulk_create(extra["objects"], batch_size=500)
                document.analysis_metadata = meta
                document.analysis_status = TextDocument.AnalysisStatus.DONE
                document.analyzed_at = timezone.now()
                document.analysis_version = PIPELINE_VERSION
                document.analysis_run = run
                document.save(update_fields=[
                    "analysis_metadata", "analysis_status", "analyzed_at", "analysis_version", "analysis_run", "updated_at",
                ])
            analyzed += 1

    fresh = max(0, usage.input_tokens - usage.cached_tokens)
    input_price, cached_price, output_price = TOKEN_PRICES_PER_MILLION[run.model_name]
    cost = (
        fresh * input_price
        + usage.cached_tokens * cached_price
        + usage.output_tokens * output_price
    ) / 1_000_000
    metric_result = {}
    if rebuild_metrics:
        try:
            until = timezone.localdate()
            metric_result = rebuild_text_metrics(
                since=until - timedelta(days=metric_days - 1),
                until=until,
            )
        except Exception as exc:
            failures += 1
            run.error_message = (
                run.error_message
                + f"\nmetrics {type(exc).__name__}: {str(exc)[:300]}"
            ).strip()
    run.analyzed_count = analyzed
    run.skipped_count = skipped
    run.failure_count = failures
    run.prompt_tokens = usage.input_tokens
    run.cached_tokens = usage.cached_tokens
    run.output_tokens = usage.output_tokens
    run.estimated_cost_usd = Decimal(str(round(cost, 6)))
    run.finished_at = timezone.now()
    run.status = (
        AnalysisPipelineRun.Status.SUCCESS if failures == 0
        else AnalysisPipelineRun.Status.PARTIAL if analyzed or skipped
        else AnalysisPipelineRun.Status.FAILED
    )
    run.metrics = {"validation_errors": validation_errors, **metric_result}
    run.save(update_fields=[
        "analyzed_count", "skipped_count", "failure_count", "prompt_tokens", "cached_tokens",
        "output_tokens", "estimated_cost_usd", "finished_at", "status", "metrics", "error_message",
    ])
    return {
        "run_id": run.id, "status": run.status, "input": len(documents), "analyzed": analyzed,
        "prefiltered": skipped, "failed": failures, "validation_errors": validation_errors,
        "estimated_cost_usd": float(run.estimated_cost_usd), "metrics": metric_result,
    }
