from __future__ import annotations
import copy
from django.db import transaction, close_old_connections, connection
from django.utils import timezone
from apps.core.models import Brand, BrandSource, Product, ProductSource, ProductTerm, DictionaryTerm, Detail
from .schemas import AgentPlan
from .repository import load_context, digest, rank_candidates, serialize_term, catalog_by_ids
from .policy import validate_changes, preview_source, gate, reconcile

class StaleAgentPlan(ValueError):
    pass

def _lock_pks(model, pks):
    pks = sorted(set(pk for pk in pks if pk is not None))

    if not pks:
        return []

    table = model._meta.db_table
    pk_column = model._meta.pk.column
    quoted_pk = connection.ops.quote_name(pk_column)

    placeholders = ", ".join(["%s"] * len(pks))

    sql = (
        f"SELECT {quoted_pk} "
        f"FROM {table} "
        f"WHERE {quoted_pk} IN ({placeholders}) "
        f"ORDER BY {quoted_pk} "
        f"FOR UPDATE"
    )

    with connection.cursor() as cursor:
        cursor.execute(sql, pks)
        locked_pks = [row[0] for row in cursor.fetchall()]

    return locked_pks


def _lock_one(model, pk):
    if pk is None:
        return None

    locked_pks = _lock_pks(model, [pk])

    if not locked_pks:
        raise model.DoesNotExist(
            f"{model.__name__} pk={pk} not found"
        )

    # 중요: PK가 아니라 실제 Django model instance 반환
    return model.objects.get(pk=pk)

def _apply_plan(*, plan, candidate_limit=None, reporter):
    """Validate again; no API calls during the DB transaction. Source raw data is preserved."""
    plan = AgentPlan.model_validate(plan)
    if not 1 <= plan.candidate_limit <= 100:
        raise ValueError('Invalid plan candidate_limit')
    if candidate_limit is not None and candidate_limit != plan.candidate_limit:
        raise ValueError('candidate_limit must match the reviewed plan')
    candidate_limit = plan.candidate_limit
    run_id = digest(plan.model_dump())
    close_old_connections()
    reporter.emit('DB_LOCK', '저장 대상 행 잠금 시작', product_source_id=plan.product_source_id)
    with transaction.atomic():
        initial = ProductSource.objects.select_related('source_brand').get(pk=plan.product_source_id)
        brand_id = initial.source_brand.brand_id if initial.source_brand_id else None
        if brand_id:
            _lock_one(Brand, pk=brand_id)
        if initial.source_brand_id:
            _lock_one(BrandSource, pk=initial.source_brand_id)
        ps = _lock_one(ProductSource, pk=initial.pk)
        attrs = copy.deepcopy(ps.attributes)
        if not isinstance(attrs,dict):
            raise ValueError('attributes must be an object')
        audit = attrs.get('_feedit_product_agent') or {}
        if audit.get('run_id') == run_id:
            reporter.emit('DB_SKIP', '이미 적용한 계획: 다시 저장하지 않음', product_source_id=ps.pk)
            return dict(status='ALREADY_APPLIED',applied=False,product_source_id=ps.pk,
                        action=audit['action'],product_id=ps.product_id,run_id=run_id)
        # Lock current links plus candidate Product records while validating/applying.
        _lock_pks(ProductTerm, pks=ProductTerm.objects.filter(product_source_id=ps.pk).values_list('pk', flat=True))
        if brand_id:
            _lock_pks(Product, pks=Product.objects.filter(brand_id=brand_id).order_by('pk').values_list('pk', flat=True))
        reporter.emit('DB_CHECK', '원본·상품 연결·후보 변경 여부 재검증')
        context = load_context(ps.pk,top_k=candidate_limit,include_catalog=False)
        addition_ids = [row.term_id for row in plan.term_review.additions]
        context['catalog'] = catalog_by_ids(addition_ids)
        if context['snapshot_hash'] != plan.snapshot_hash or context['candidate_universe_hash'] != plan.candidate_universe_hash:
            reporter.emit('DB_STALE', '검수 후 데이터 변경 감지: 저장 중단')
            raise StaleAgentPlan('Source, ProductTerms, brand or candidate Products changed; regenerate the plan.')
        changes = validate_changes(context,plan.name_review,plan.attribute_review,plan.term_review)
        cleaned = preview_source(context,changes)
        context['candidates'],context['exact_style_product_ids'] = rank_candidates(cleaned,context['_products'],candidate_limit)
        issues = plan.name_review.issues + plan.attribute_review.issues + plan.term_review.issues
        validated = gate(context,plan.identity_review,issues=issues)
        decision = reconcile(validated,plan.decision)
        if decision.action != plan.decision.action or decision.product_id != plan.decision.product_id:
            raise ValueError('Plan decision violates current validated policy')
        # Dictionary rows are independent from source timestamps: validate additions under their own locks.
        catalog = {t['term_id']:t for t in context['catalog']}
        for addition in changes['add_terms']:
            reporter.emit('DB_TERM_CHECK', '추가 용어 상태·관계 검증', term_id=addition['term_id'])
            term = _lock_one(DictionaryTerm, pk=addition['term_id'])
            # Lock the nullable Detail row separately: never FOR UPDATE an outer join.
            _lock_pks(Detail, pks=Detail.objects.filter(term_id=term.pk).values_list('pk', flat=True))
            if serialize_term(term) != catalog[term.pk]:
                raise StaleAgentPlan('Dictionary term changed during apply')
        before = dict(fields={k:getattr(ps,k) for k in changes['fields']},attributes=copy.deepcopy(ps.attributes),
                      removed_terms=[t for t in context['source']['terms'] if t['product_term_id'] in changes['remove_term_ids']],
                      product_id=ps.product_id)
        for field,value in changes['fields'].items():
            reporter.emit('DB_FIELD', '상품 정보 반영', field=field, before=getattr(ps,field), after=value)
            setattr(ps,field,value)
        normalized = attrs.get('normalized')
        if normalized is None:
            normalized = attrs['normalized'] = {}
        for key, value in changes['attributes'].items():
            reporter.emit('DB_ATTRIBUTE', '빈 표준 속성 보완', key=key, value=value)
        normalized.update(changes['attributes'])
        for row in before['removed_terms']:
            reporter.emit('DB_TERM_DELETE', '잘못된 상품-용어 연결 삭제', product_term_id=row['product_term_id'], term=row['canonical_name'], relation=row['relation_type'])
        ProductTerm.objects.filter(product_source_id=ps.pk,pk__in=changes['remove_term_ids']).delete()
        created_links = []
        for addition in changes['add_terms']:
            link,created = ProductTerm.objects.get_or_create(product_source_id=ps.pk,**addition)
            reporter.emit('DB_TERM_ADD', '용어 연결 처리', term_id=addition['term_id'], relation=addition['relation_type'], created=created)
            if created:
                created_links.append(link.pk)
        if decision.action == 'MAP':
            _lock_one(Product, pk=decision.product_id)
            product = Product.objects.get(pk=decision.product_id, brand_id=brand_id, status='ACTIVE')
            ps.product_id = product.pk
            reporter.emit('DB_MAP', '기존 Product 연결', product_id=product.pk, name=product.canonical_name)
        elif decision.action == 'PROMOTE':
            name = ps.normalized_name or ps.source_name
            product = Product.objects.create(brand_id=brand_id,category_id=context['source']['category_id'],
                canonical_name=name,normalized_name=name,english_name=ps.source_name_en,
                gender_scope=ps.gender_scope,attributes=copy.deepcopy(normalized))
            # Independent FEEDIT identity, never use a potentially non-unique platform style_no.
            product.product_code = f'FEEDIT_{brand_id}_{product.pk:010d}'
            product.save(update_fields=['product_code','updated_at'])
            ps.product_id = product.pk
            reporter.emit('DB_PROMOTE', '신규 Product 생성', product_id=product.pk, product_code=product.product_code, name=product.canonical_name)
        elif decision.action == 'HOLD':
            reporter.emit('DB_HOLD', '상품 연결은 보류, 검증된 정보·term 교정만 반영', reasons=decision.reasons)
        else:
            reporter.emit('DB_KEEP', '기존 Product 연결 유지', product_id=ps.product_id)
        ps.mapping_status = 'MAPPED' if ps.product_id else 'UNMAPPED'
        # Bounded, persistent audit without adding a table or altering raw source attributes.
        prior = copy.deepcopy(audit)
        prior.pop('history',None)
        history = (audit.get('history') or [])[-3:]
        if prior:
            history.append(prior)
        # Avoid recursively duplicating audit history inside before.attributes.
        before['attributes'].pop('_feedit_product_agent',None)
        attrs['_feedit_product_agent'] = dict(version=1,run_id=run_id,applied_at=timezone.now().isoformat(),
            action=decision.action,reasons=decision.reasons,plan=plan.model_dump(),changes=changes,
            before=before,created_product_term_ids=created_links,history=history)
        ps.attributes = attrs
        ps.save(update_fields=list(changes['fields'])+['attributes','product','mapping_status','updated_at'])
        return dict(status='APPLIED',applied=True,product_source_id=ps.pk,action=decision.action,
                    product_id=ps.product_id,run_id=run_id,plan=plan.model_dump(),changes=changes)


def apply_plan(*, plan, candidate_limit=None, log=print, verbose=True, reporter=None):
    """Public writer: success is reported only after the transaction commits."""
    from .reporting import ProgressReporter
    reporter = reporter or ProgressReporter(log=log, verbose=verbose)
    try:
        result = _apply_plan(plan=plan, candidate_limit=candidate_limit, reporter=reporter)
    except Exception as exc:
        reporter.emit('DB_FAILED', '저장 실패: 이 실행의 트랜잭션 변경 롤백', error_type=type(exc).__name__, error=str(exc))
        raise
    reporter.emit('DB_DONE', '저장 처리 완료', status=result['status'], action=result['action'],
                  product_source_id=result['product_source_id'], product_id=result['product_id'])
    result['report'] = list(reporter.events)
    return result
