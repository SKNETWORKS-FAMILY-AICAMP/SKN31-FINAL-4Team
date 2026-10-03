from __future__ import annotations
import copy
import hashlib
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher

from django.db.models import Prefetch
from apps.core.models import Product, ProductSource, ProductTerm, DictionaryTerm

SUPPORTED = {'musinsa','kream','zigzag','ably','musinsa_used'}


def code(value):
    return str(value or '').strip().lower().replace('-', '_')


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '').strip().casefold())


def name_key(value):
    return clean(re.sub(r'[^0-9A-Za-z가-힣]+', ' ', str(value or '')))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def serialize_term(term):
    detail = getattr(term, 'detail', None)
    return dict(term_id=term.pk, term_type=term.term_type, canonical_name=term.canonical_name,
                english_name=term.english_name, description=term.description, status=term.status,
                detail_attribute_type=getattr(detail, 'attribute_type', None))


def serialize_source(ps, *, terms=None):
    terms = list(ps.product_terms.all()) if terms is None else terms
    return dict(product_source_id=ps.pk, product_id=ps.product_id, source_code=code(ps.source.code),
                source_product_id=ps.source_product_id, mapping_status=ps.mapping_status,
                source_name=ps.source_name, normalized_name=ps.normalized_name, source_name_en=ps.source_name_en,
                style_no=ps.style_no, gender_scope=ps.gender_scope, season_year=ps.season_year, season=ps.season,
                source_genders=ps.source_genders, attributes=copy.deepcopy(ps.attributes), status=ps.status,
                source_brand_id=ps.source_brand_id,
                brand_id=ps.source_brand.brand_id if ps.source_brand_id else None,
                brand_mapping_status=ps.source_brand.mapping_status if ps.source_brand_id else None,
                brand_status=ps.source_brand.brand.status if ps.source_brand_id and ps.source_brand.brand_id else None,
                source_category_id=ps.source_category_id,
                category_id=ps.source_category.category_id if ps.source_category_id else None,
                thumbnail_url=ps.thumbnail_url, market_type=ps.market_type, updated_at=str(ps.updated_at),
                terms=[dict(product_term_id=pt.pk, relation_type=pt.relation_type,
                            **serialize_term(pt.term)) for pt in terms])


def source_queryset():
    terms = ProductTerm.objects.select_related('term', 'term__detail').order_by('pk')
    return ProductSource.objects.select_related('source','source_brand','source_brand__brand','source_category').prefetch_related(
        Prefetch('product_terms', queryset=terms)).order_by('pk')


def evidence_sources(source):
    """Only source text/attributes can support extraction, never model output/term labels/IDs."""
    out = {}
    def walk(path, value):
        if isinstance(value, dict):
            for k, v in value.items():
                if str(k).startswith('_feedit_'):
                    continue
                walk(f'{path}.{k}', v)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(f'{path}.{i}', v)
        elif value is not None and str(value).strip():
            out[path] = str(value)[:6000]
    for key in ('source_name','normalized_name','source_name_en','style_no','gender_scope','season','season_year','source_genders','attributes'):
        walk(key, source[key])
    return out


def product_records(brand_id):
    if not brand_id:
        return []
    products = Product.objects.filter(brand_id=brand_id, status='ACTIVE').prefetch_related(
        Prefetch('sources', queryset=source_queryset())).order_by('pk')
    return [dict(product_id=p.pk, brand_id=p.brand_id, normalized_name=p.normalized_name,
                 canonical_name=p.canonical_name, english_name=p.english_name, gender_scope=p.gender_scope,
                 attributes=copy.deepcopy(p.attributes), category_id=p.category_id,
                 product_code=p.product_code, updated_at=str(p.updated_at),
                 sources=[serialize_source(ps) for ps in p.sources.all()]) for p in products]


def rank_candidates(source, products, top_k):
    target_style = clean(source['style_no'])
    target_name = name_key(source['normalized_name'] or source['source_name'])
    scores = []
    exact_style_ids = []
    for p in products:
        names = [p['normalized_name'], p['canonical_name'], p['english_name']]
        for ps in p['sources']:
            if ps['source_code'] != 'musinsa_used':
                names.extend([ps['normalized_name'], ps['source_name'], ps['source_name_en']])
        style_exact = bool(target_style and any(clean(ps['style_no']) == target_style for ps in p['sources']))
        exact_name = bool(target_name and any(name_key(n) == target_name for n in names if n))
        similarity = max((SequenceMatcher(None, target_name, name_key(n)).ratio() for n in names if n), default=0)
        rank = (2 if style_exact else 0) + (1 if exact_name else 0) + similarity
        scores.append((rank, p['product_id'], dict(p, retrieval_style_exact=style_exact, retrieval_name_exact=exact_name)))
        if style_exact:
            exact_style_ids.append(p['product_id'])
    scores.sort(key=lambda row: (-row[0], row[1]))
    selected = scores[:top_k]
    selected_ids = {row[1] for row in selected}
    # All style/name exact candidates must survive top-k for ambiguity checks.
    selected.extend(row for row in scores[top_k:] if row[2]['retrieval_style_exact'] or row[2]['retrieval_name_exact'])
    return [row[2] for row in selected], exact_style_ids


def term_catalog(source, *, limit=120):
    """Build the prompt catalog with one flat SQL query instead of instantiating every term/alias object."""
    text = name_key(' '.join(evidence_sources(source).values()))
    current = {row['term_id'] for row in source['terms']}
    rows = DictionaryTerm.objects.filter(status='ACTIVE').values(
        'pk', 'term_type', 'canonical_name', 'english_name', 'normalized_name',
        'description', 'status', 'detail__attribute_type', 'aliases__alias',
    ).order_by('pk')
    grouped = {}
    for row in rows.iterator(chunk_size=2000):
        pk = row['pk']
        item = grouped.get(pk)
        if item is None:
            item = grouped[pk] = dict(
                term_id=pk, term_type=row['term_type'], canonical_name=row['canonical_name'],
                english_name=row['english_name'], description=row['description'], status=row['status'],
                detail_attribute_type=row['detail__attribute_type'], aliases=[])
        alias = row['aliases__alias']
        if alias:
            item['aliases'].append(alias)
    scored = []
    for pk, item in grouped.items():
        words = [item['canonical_name'], item['english_name']]
        words.extend(item.pop('aliases'))
        hits = [len(name_key(w)) for w in words if w and len(name_key(w)) > 1 and name_key(w) in text]
        if pk in current or hits:
            scored.append((10000 if pk in current else max(hits), pk, item))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in scored[:limit]]


def catalog_by_ids(term_ids):
    ids = sorted({int(pk) for pk in term_ids if pk is not None})
    if not ids:
        return []
    return [serialize_term(term) for term in DictionaryTerm.objects.filter(pk__in=ids).select_related('detail').order_by('pk')]


def load_context(product_source_id, *, top_k=12, include_catalog=True):
    source = serialize_source(source_queryset().get(pk=product_source_id))
    products = product_records(source['brand_id'])
    candidates, style_ids = rank_candidates(source, products, top_k)
    return dict(source=source, snapshot_hash=digest(source), candidates=candidates,
                candidate_universe_hash=digest(products), candidate_total=len(products),
                candidate_retrieval='full-brand lexical/style scan; limited semantic comparison',
                exact_style_product_ids=style_ids, evidence_sources=evidence_sources(source), catalog=term_catalog(source) if include_catalog else [], _products=products)
