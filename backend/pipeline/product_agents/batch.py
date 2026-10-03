from __future__ import annotations
from collections import Counter
from django.db import close_old_connections
from django.db.models import Case, When, Value, IntegerField, Q
from apps.core.models import Brand, ProductSource
from .orchestrator import ProductAgentOrchestrator

PRIORITY = Case(When(source__code__iexact='musinsa',then=Value(0)),
    When(source__code__iexact='kream',then=Value(1)),
    When(source__code__iexact='zigzag',then=Value(2)),
    When(source__code__iexact='ably',then=Value(3)),default=Value(4),output_field=IntegerField())
SOURCE_FILTER = Q(source__code__iexact='musinsa') | Q(source__code__iexact='kream') | Q(source__code__iexact='zigzag') | Q(source__code__iexact='ably') | Q(source__code__iexact='musinsa_used') | Q(source__code__iexact='musinsa-used')


def run_product_agent_batch(*, brand_batch_size=10, max_products=50, after_brand_id=0,
                            cursor=None, brand_ids=None, apply=False, model=None, reviewer=None,
                            candidate_limit=12, include_linked=True, log=print, verbose=True):
    """One bounded batch. Cursor advances past attempted records, including failures."""
    if isinstance(brand_batch_size,bool) or not isinstance(brand_batch_size,int) or brand_batch_size<1:
        raise ValueError('brand_batch_size must be a positive integer')
    if isinstance(max_products,bool) or not isinstance(max_products,int) or max_products<1:
        raise ValueError('max_products must be a positive integer')
    cursor = dict(cursor or {})
    after_brand_id = int(cursor.get('after_brand_id',after_brand_id))
    resume_brand = cursor.get('resume_brand_id')
    after_priority = int(cursor.get('after_source_priority',-1))
    after_ps = int(cursor.get('after_product_source_id',0))
    sources = ProductSource.objects.filter(SOURCE_FILTER,status='ACTIVE',source_brand__brand_id__isnull=False)
    if not include_linked:
        sources = sources.filter(product_id__isnull=True)
    qs = Brand.objects.filter(pk__in=sources.values('source_brand__brand_id')).order_by('pk')
    if brand_ids is not None:
        qs = qs.filter(pk__in=list(brand_ids))
    qs = qs.filter(pk__gte=resume_brand) if resume_brand else qs.filter(pk__gt=after_brand_id)
    ids = list(qs.values_list('pk',flat=True)[:brand_batch_size+1])
    selected = ids[:brand_batch_size]
    orchestrator = ProductAgentOrchestrator(reviewer=reviewer,model=model,candidate_limit=candidate_limit,log=log,verbose=verbose)
    outcomes,errors = [],[]
    completed_brand = after_brand_id
    next_cursor = dict(after_brand_id=after_brand_id,resume_brand_id=None,after_source_priority=-1,after_product_source_id=0)
    stopped = False
    for index,bid in enumerate(selected,1):
        log(f'[{index}/{len(selected)}] BRAND {bid} START')
        ps_qs = sources.filter(source_brand__brand_id=bid).annotate(agent_priority=PRIORITY)
        if bid == resume_brand:
            ps_qs = ps_qs.filter(Q(agent_priority__gt=after_priority)|Q(agent_priority=after_priority,pk__gt=after_ps))
        # Snapshot only the bounded remaining IDs; no long-lived DB cursor during LLM calls.
        budget = max_products-len(outcomes)-len(errors)
        ps_ids = list(ps_qs.order_by('agent_priority','pk').values_list('pk','agent_priority')[:budget+1])
        attempted = ps_ids[:budget]
        for ps_id,priority in attempted:
            try:
                outcomes.append(orchestrator.run(product_source_id=ps_id,apply=apply))
            except Exception as exc:
                errors.append(dict(product_source_id=ps_id,brand_id=bid,error_type=type(exc).__name__,error=str(exc)))
                log(f'PS {ps_id} FAILED {type(exc).__name__}: {exc}')
            finally:
                close_old_connections()
            next_cursor = dict(after_brand_id=completed_brand,resume_brand_id=bid,
                               after_source_priority=priority,after_product_source_id=ps_id)
        if len(ps_ids)>budget:
            stopped=True
            break
        completed_brand=bid
        next_cursor=dict(after_brand_id=bid,resume_brand_id=None,after_source_priority=-1,after_product_source_id=0)
        if len(outcomes)+len(errors)>=max_products:
            stopped=index<len(selected) or len(ids)>brand_batch_size
            break
    has_more = stopped or len(ids)>brand_batch_size
    log(f"BATCH DONE | attempted={len(outcomes)+len(errors)} success={len(outcomes)} failed={len(errors)} actions={dict(Counter(r['action'] for r in outcomes))} next_cursor={next_cursor}")
    return dict(applied=apply,results=outcomes,errors=errors,failed_product_source_ids=[e['product_source_id'] for e in errors],
                totals=dict(Counter(r['action'] for r in outcomes)),attempted_products=len(outcomes)+len(errors),
                selected_brand_ids=selected,next_cursor=next_cursor,has_more=has_more)
