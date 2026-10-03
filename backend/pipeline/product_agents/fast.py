from __future__ import annotations

from collections import Counter
from django.db import transaction, close_old_connections
from django.db.models import Q

from apps.core.models import Brand, BrandSource, Product, ProductSource
from .repository import clean, name_key, code
from .writer import _lock_one, _lock_pks

SUPPORTED = {'musinsa','kream','zigzag','ably','musinsa_used'}
PROMOTABLE = {'musinsa','kream','zigzag','ably'}


def _base_source(ps_id):
    return (ProductSource.objects
            .select_related('source','source_brand','source_brand__brand','source_category')
            .get(pk=ps_id))


def _candidate_qs(ps):
    brand_id = ps.source_brand.brand_id if ps.source_brand_id else None
    if not brand_id:
        return Product.objects.none()
    return Product.objects.filter(brand_id=brand_id, status='ACTIVE')


def _exact_style_products(ps):
    style = clean(ps.style_no)
    if not style:
        return []
    # style_no is platform identity evidence. Exclude USED observations as identity anchors.
    ids = (ProductSource.objects
           .filter(product_id__isnull=False,
                   product__brand_id=ps.source_brand.brand_id,
                   product__status='ACTIVE')
           .exclude(Q(source__code__iexact='musinsa_used') | Q(source__code__iexact='musinsa-used'))
           .values('product_id','style_no'))
    return sorted({row['product_id'] for row in ids if clean(row['style_no']) == style})


def _exact_name_products(ps):
    target = name_key(ps.normalized_name or ps.source_name)
    if not target:
        return []
    products = _candidate_qs(ps).values('pk','normalized_name','canonical_name')
    return sorted({row['pk'] for row in products
                   if target in {name_key(row['normalized_name']), name_key(row['canonical_name'])}})


def decide_fast(ps):
    source_code = code(ps.source.code)
    brand_id = ps.source_brand.brand_id if ps.source_brand_id else None
    if ps.product_id:
        return 'KEEP', ps.product_id, 'Existing Product link preserved'
    if ps.status != 'ACTIVE' or source_code not in SUPPORTED:
        return 'HOLD', None, 'Unsupported source or inactive ProductSource'
    if not brand_id or ps.source_brand.mapping_status == 'EXCLUDED' or ps.source_brand.brand.status != 'ACTIVE':
        return 'HOLD', None, 'FEEDIT brand missing, excluded, or inactive'
    if not (str(ps.normalized_name or ps.source_name or '').strip()):
        return 'HOLD', None, 'Product name missing'

    style_ids = _exact_style_products(ps)
    if len(style_ids) == 1:
        return 'MAP', style_ids[0], 'Unique exact style_no match'
    if len(style_ids) > 1:
        return 'HOLD', None, f'Ambiguous exact style_no match: {style_ids}'

    name_ids = _exact_name_products(ps)
    if len(name_ids) == 1:
        return 'MAP', name_ids[0], 'Unique exact normalized/canonical name match'
    if len(name_ids) > 1:
        return 'HOLD', None, f'Ambiguous exact name match: {name_ids}'

    if source_code in PROMOTABLE:
        return 'PROMOTE', None, 'No exact existing Product match; fast promotion policy'
    return 'HOLD', None, 'USED promotion disabled without an exact existing Product match'


def run_product_agent_fast(*, product_source_id, apply=False, log=print, verbose=True):
    ps = _base_source(product_source_id)
    action, product_id, reason = decide_fast(ps)
    if verbose:
        log(f'FAST_DECISION | ps={ps.pk} source={code(ps.source.code)} action={action} product_id={product_id} reason={reason}')
    if not apply:
        return dict(status='PLANNED', applied=False, product_source_id=ps.pk,
                    action=action, product_id=product_id, reason=reason)

    close_old_connections()
    with transaction.atomic():
        initial = _base_source(product_source_id)
        brand_id = initial.source_brand.brand_id if initial.source_brand_id else None
        if brand_id:
            _lock_one(Brand, brand_id)
        if initial.source_brand_id:
            _lock_one(BrandSource, initial.source_brand_id)
        ps = _lock_one(ProductSource, initial.pk)
        # Reload relations after raw row lock.
        ps = _base_source(ps.pk)
        current_action, current_pid, current_reason = decide_fast(ps)
        if (current_action, current_pid) != (action, product_id):
            action, product_id, reason = current_action, current_pid, current_reason
            if verbose:
                log(f'FAST_RECHECK | ps={ps.pk} action={action} product_id={product_id} reason={reason}')

        if action == 'MAP':
            _lock_one(Product, product_id)
            product = Product.objects.get(pk=product_id, brand_id=brand_id, status='ACTIVE')
            ps.product_id = product.pk
        elif action == 'PROMOTE':
            name = ps.normalized_name or ps.source_name
            category_id = ps.source_category.category_id if ps.source_category_id else None
            attrs = ps.attributes if isinstance(ps.attributes, dict) else {}
            normalized = attrs.get('normalized') if isinstance(attrs.get('normalized'), dict) else {}
            product = Product.objects.create(
                brand_id=brand_id,
                category_id=category_id,
                canonical_name=name,
                normalized_name=name,
                english_name=ps.source_name_en,
                gender_scope=ps.gender_scope,
                attributes=normalized.copy(),
            )
            product.product_code = f'FEEDIT_{brand_id}_{product.pk:010d}'
            product.save(update_fields=['product_code','updated_at'])
            ps.product_id = product.pk
            product_id = product.pk

        ps.mapping_status = 'MAPPED' if ps.product_id else 'UNMAPPED'
        ps.save(update_fields=['product','mapping_status','updated_at'])

    if verbose:
        log(f'FAST_DONE | ps={product_source_id} action={action} product_id={product_id}')
    return dict(status='APPLIED', applied=True, product_source_id=product_source_id,
                action=action, product_id=product_id, reason=reason)


def run_product_agent_fast_batch(*, max_products=500, after_product_source_id=0,
                                 source_codes=None, brand_ids=None, apply=False,
                                 include_linked=False, log=print, verbose=False):
    if isinstance(max_products, bool) or not isinstance(max_products, int) or max_products < 1:
        raise ValueError('max_products must be a positive integer')
    qs = (ProductSource.objects
          .filter(status='ACTIVE', pk__gt=after_product_source_id,
                  source_brand__brand_id__isnull=False)
          .order_by('pk'))
    if not include_linked:
        qs = qs.filter(product_id__isnull=True)
    codes = [code(x) for x in (source_codes or SUPPORTED)]
    source_q = Q()
    for value in codes:
        source_q |= Q(source__code__iexact=value) | Q(source__code__iexact=value.replace('_','-'))
    qs = qs.filter(source_q)
    if brand_ids is not None:
        qs = qs.filter(source_brand__brand_id__in=list(brand_ids))
    ids = list(qs.values_list('pk', flat=True)[:max_products + 1])
    selected = ids[:max_products]
    results, errors = [], []
    for index, ps_id in enumerate(selected, 1):
        if verbose:
            log(f'FAST_BATCH [{index}/{len(selected)}] PS {ps_id}')
        try:
            results.append(run_product_agent_fast(product_source_id=ps_id, apply=apply, log=log, verbose=verbose))
        except Exception as exc:
            errors.append(dict(product_source_id=ps_id, error_type=type(exc).__name__, error=str(exc)))
            log(f'FAST_BATCH_FAILED | ps={ps_id} {type(exc).__name__}: {exc}')
        finally:
            close_old_connections()
    totals = dict(Counter(row['action'] for row in results))
    next_id = selected[-1] if selected else after_product_source_id
    log(f'FAST_BATCH_DONE | attempted={len(selected)} success={len(results)} failed={len(errors)} actions={totals} next={next_id}')
    return dict(applied=apply, results=results, errors=errors, totals=totals,
                attempted_products=len(selected), next_product_source_id=next_id,
                has_more=len(ids) > max_products)
