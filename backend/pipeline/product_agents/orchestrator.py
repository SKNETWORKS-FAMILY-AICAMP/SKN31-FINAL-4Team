from __future__ import annotations
import copy
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from time import perf_counter

from . import prompts
from .llm import OpenAIReviewer
from .policy import validate_changes, preview_source, gate, reconcile
from .repository import load_context, rank_candidates
from .reporting import ProgressReporter
from .schemas import AgentPlan, NameReview, AttributeReview, TermReview, IdentityReview, FinalDecision

ROLE_NAMES = {'name':'상품명·기본 정보 검수','attributes':'빈 속성 보완','terms':'DictionaryTerm 연결 검수',
              'identity':'기존 Product 동일성 비교','decision':'매핑·승격·보류 최종 결정'}

class ProductAgentOrchestrator:
    def __init__(self, *, reviewer=None, model=None, candidate_limit=12, max_input_chars=180000,
                 log=print, verbose=True):
        if not 1 <= candidate_limit <= 100:
            raise ValueError('candidate_limit must be 1..100')
        self.reviewer = reviewer or OpenAIReviewer(model=model)
        self.candidate_limit = candidate_limit
        self.max_input_chars = max_input_chars
        self.log = log
        self.verbose = verbose
        self.reporter = None

    def _review(self, role, prompt, payload, schema):
        def scrub(value):
            if isinstance(value, dict):
                return {k:scrub(v) for k,v in value.items() if not str(k).startswith('_feedit_')}
            if isinstance(value, list):
                return [scrub(v) for v in value]
            return value
        payload = scrub(payload)
        chars = len(json.dumps(payload, ensure_ascii=False, default=str))
        if chars > self.max_input_chars:
            raise ValueError(f'{role}: input too large; reduce catalog/candidates or inspect this ProductSource')
        started = perf_counter()
        self.reporter.emit('AGENT_START', ROLE_NAMES[role], role=role, input_chars=chars)
        try:
            with ThreadPoolExecutor(max_workers=1) as api_pool:
                future = api_pool.submit(self.reviewer.review,role=role,prompt=prompt,payload=payload,schema=schema)
                while True:
                    try:
                        result = future.result(timeout=15)
                        break
                    except FutureTimeout:
                        if future.done():
                            raise
                        self.reporter.emit('AGENT_WAIT','GPT 응답 대기 중',role=role,task=ROLE_NAMES[role],seconds=round(perf_counter()-started,1))
            validated = schema.model_validate(result)
        except Exception as exc:
            self.reporter.emit('AGENT_FAILED',ROLE_NAMES[role],role=role,error_type=type(exc).__name__,error=str(exc))
            raise
        self.reporter.emit('AGENT_DONE', ROLE_NAMES[role], role=role,
                           seconds=round(perf_counter()-started,2), usage=getattr(result,'_usage',{}))
        return validated

    def _report_changes(self, context, changes, name, attributes, terms):
        report = self.reporter
        source = context['source']
        report.emit('VALIDATE', '원문 근거·빈 값·용어 ID·관계 유형 검증 완료',
                    fields=len(changes['fields']),attributes=len(changes['attributes']),
                    remove_terms=len(changes['remove_term_ids']),add_terms=len(changes['add_terms']),
                    rejected=len(changes['rejected']))
        for field,value in changes['fields'].items():
            patch = next(p for p in name.patches if p.field==field)
            report.emit('FIELD_PLAN','상품 정보 변경안',detail=True,field=field,before=source[field],after=value,
                        evidence_path=patch.evidence.path,quote=patch.evidence.quote,reason=patch.evidence.explanation)
        for key,value in changes['attributes'].items():
            patch = next(p for p in attributes.patches if p.key==key)
            report.emit('ATTRIBUTE_PLAN','빈 속성 보완안',detail=True,key=key,values=value,
                        evidence_path=patch.evidence.path,quote=patch.evidence.quote,reason=patch.evidence.explanation)
        links = {t['product_term_id']:t for t in source['terms']}
        for link_id in changes['remove_term_ids']:
            row = links[link_id]
            removal = next(p for p in terms.removals if p.product_term_id==link_id)
            report.emit('TERM_DELETE_PLAN','상품-용어 연결 삭제안',detail=True,product_term_id=link_id,
                        term=row['canonical_name'],relation=row['relation_type'],quote=removal.evidence.quote,
                        reason=removal.evidence.explanation)
        catalog = {t['term_id']:t for t in context['catalog']}
        for row in changes['add_terms']:
            addition = next(p for p in terms.additions if p.term_id==row['term_id'] and p.relation_type==row['relation_type'])
            report.emit('TERM_ADD_PLAN','상품-용어 연결 추가안',detail=True,term_id=row['term_id'],
                        term=catalog[row['term_id']]['canonical_name'],relation=row['relation_type'],
                        quote=addition.evidence.quote,reason=addition.evidence.explanation)
        for row in changes['rejected']:
            report.emit('PROPOSAL_REJECTED','검증 조건 불충족: 이 변경은 적용하지 않음',detail=True,
                        kind=row['kind'],proposal=row['proposal'],reason=row['reason'])
        for role,review in [('name',name),('attributes',attributes),('terms',terms)]:
            for issue in review.issues:
                report.emit('REVIEW_ISSUE','검수 이슈',role=role,issue=issue)

    def plan(self, *, product_source_id):
        self.reporter = ProgressReporter(log=self.log,verbose=self.verbose)
        report = self.reporter
        report.emit('LOAD_START','ProductSource·속성·용어·같은 브랜드 상품 조회',product_source_id=product_source_id)
        context = load_context(product_source_id, top_k=self.candidate_limit)
        source = context['source']
        report.emit('SOURCE','대상 상품',product_source_id=product_source_id,source=source['source_code'],
                    brand_id=source['brand_id'],existing_product_id=source['product_id'],market_type=source['market_type'])
        report.emit('SOURCE_NAME','원본·정규화 상품명',source_name=source['source_name'],
                    normalized_name=source['normalized_name'],style_no=source['style_no'])
        report.emit('SOURCE_FIELDS','기본 정보',detail=True,gender=source['gender_scope'],
                    season_year=source['season_year'],season=source['season'])
        report.emit('LOAD_DONE','조회 완료',linked_terms=len(source['terms']),catalog_terms=len(context['catalog']),
                    brand_products=context['candidate_total'],comparison_candidates=len(context['candidates']))
        for row in source['terms']:
            report.emit('CURRENT_TERM','현재 연결 용어',detail=True,product_term_id=row['product_term_id'],
                        term=row['canonical_name'],term_type=row['term_type'],relation=row['relation_type'])
        source_for_prompt = copy.deepcopy(source)
        source_for_prompt['attributes'].pop('_feedit_product_agent', None)
        base = dict(source=source_for_prompt, evidence_sources=context['evidence_sources'], catalog=context['catalog'])
        jobs = [('name',prompts.NAME,NameReview),('attributes',prompts.ATTRIBUTES,AttributeReview),('terms',prompts.TERMS,TermReview)]
        report.emit('PARALLEL_START','상품 정보·속성·용어 검수 에이전트 3개 병렬 실행')
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(self._review, role, prompt, base, schema) for role,prompt,schema in jobs]
            name, attributes, terms = [f.result() for f in futures]
        changes = validate_changes(context, name, attributes, terms)
        self._report_changes(context,changes,name,attributes,terms)
        cleaned = preview_source(context, changes)
        context['candidates'], context['exact_style_product_ids'] = rank_candidates(cleaned, context['_products'], self.candidate_limit)
        cleaned['attributes'].pop('_feedit_product_agent', None)
        report.emit('CANDIDATE_SEARCH','정리된 상품명·품번으로 후보 재정렬',brand_products=context['candidate_total'],
                    candidate_count=len(context['candidates']),style_exact_ids=context['exact_style_product_ids'])
        for candidate in context['candidates']:
            report.emit('CANDIDATE','비교 대상 Product',detail=True,product_id=candidate['product_id'],
                        name=candidate['canonical_name'],style_exact=candidate['retrieval_style_exact'],
                        name_exact=candidate['retrieval_name_exact'])
        if source['product_id'] is not None:
            identity = IdentityReview(assessments=[],distinct_product=False,confidence='HIGH',reasons=['Already linked'],conflicts=[])
            report.emit('IDENTITY_SKIP','기존 연결 상품: 재매핑 판단 생략',product_id=source['product_id'])
        else:
            identity = self._review('identity',prompts.IDENTITY,
                dict(source=cleaned,candidates=context['candidates'],candidate_total=context['candidate_total'],
                     retrieval=context['candidate_retrieval'],evidence_sources=context['evidence_sources']),IdentityReview)
            expected_ids = {row['product_id'] for row in context['candidates']}
            assessed_ids = [row.product_id for row in identity.assessments]
            missing_ids = expected_ids - set(assessed_ids)
            duplicate_ids = {pk for pk in assessed_ids if assessed_ids.count(pk) > 1}
            unexpected_ids = set(assessed_ids) - expected_ids
            if missing_ids and not duplicate_ids and not unexpected_ids:
                missing_candidates = [row for row in context['candidates'] if row['product_id'] in missing_ids]
                report.emit('IDENTITY_RETRY','누락 후보만 동일성 재검수',missing_product_ids=sorted(missing_ids))
                supplement = self._review('identity',prompts.IDENTITY,
                    dict(source=cleaned,candidates=missing_candidates,candidate_total=len(missing_candidates),
                         retrieval='missing candidates retry',evidence_sources=context['evidence_sources']),IdentityReview)
                supplement_ids = [row.product_id for row in supplement.assessments]
                if set(supplement_ids) == missing_ids and len(supplement_ids) == len(missing_ids):
                    merged = list(identity.assessments) + list(supplement.assessments)
                    any_same = any(row.verdict == 'SAME' for row in merged)
                    any_uncertain = any(row.verdict == 'UNCERTAIN' or row.conflicts or row.confidence != 'HIGH' for row in merged)
                    identity = IdentityReview(
                        assessments=merged,
                        distinct_product=(not any_same and not any_uncertain and identity.distinct_product and supplement.distinct_product),
                        confidence='HIGH' if identity.confidence == supplement.confidence == 'HIGH' else 'MEDIUM',
                        reasons=list(identity.reasons) + list(supplement.reasons),
                        conflicts=list(identity.conflicts) + list(supplement.conflicts),
                    )
                    report.emit('IDENTITY_RETRY_DONE','누락 후보 검수 병합 완료',assessment_count=len(identity.assessments))
        for assessment in identity.assessments:
            report.emit('IDENTITY_RESULT','후보별 동일성 판단',detail=True,product_id=assessment.product_id,
                        verdict=assessment.verdict,confidence=assessment.confidence,
                        reasons=assessment.reasons,conflicts=assessment.conflicts)
        report.emit('IDENTITY_SUMMARY','동일 상품 비교 결과',distinct_product=identity.distinct_product,
                    confidence=identity.confidence,reasons=identity.reasons,conflicts=identity.conflicts)
        issues = name.issues + attributes.issues + terms.issues
        gated = gate(context, identity, issues=issues)
        report.emit('POLICY','플랫폼·기존 연결·모호성 규칙 검증',action=gated.action,product_id=gated.product_id,reasons=gated.reasons)
        if gated.action == 'KEEP':
            decision = gated
        else:
            proposed = self._review('decision',prompts.DECISION,
                dict(source=cleaned,identity=identity.model_dump(),issues=issues,
                     deterministic_gate=gated.model_dump()),FinalDecision)
            decision = reconcile(gated,proposed)
            if proposed.action != decision.action or proposed.product_id != decision.product_id:
                report.emit('DECISION_GUARD','최종 모델 제안을 규칙에 맞게 제한',
                            proposed=proposed.model_dump(),validated=decision.model_dump())
        plan = AgentPlan(product_source_id=product_source_id,candidate_limit=self.candidate_limit,snapshot_hash=context['snapshot_hash'],
            candidate_universe_hash=context['candidate_universe_hash'],name_review=name,attribute_review=attributes,
            term_review=terms,identity_review=identity,decision=decision)
        report.emit('DECISION','최종 결정',action=decision.action,product_id=decision.product_id,
                    confidence=decision.confidence,reasons=decision.reasons)
        return plan, context, changes

    def run(self, *, product_source_id, apply=False):
        try:
            plan, context, changes = self.plan(product_source_id=product_source_id)
            if apply:
                from .writer import apply_plan
                return apply_plan(plan=plan,candidate_limit=self.candidate_limit,reporter=self.reporter)
            self.reporter.emit('PREVIEW_DONE','검수 계획만 반환: DB 변경 없음',product_source_id=product_source_id)
            return dict(status='PLANNED',applied=False,product_source_id=product_source_id,
                        action=plan.decision.action,product_id=plan.decision.product_id,
                        plan=plan.model_dump(),changes=changes,report=list(self.reporter.events),
                        candidate_total=context['candidate_total'],candidate_count=len(context['candidates']))
        except Exception as exc:
            if self.reporter is not None:
                self.reporter.emit('FAILED','상품 처리 실패',product_source_id=product_source_id,
                                   error_type=type(exc).__name__,error=str(exc))
            raise


def run_product_agent(*, product_source_id, apply=False, model=None, reviewer=None,candidate_limit=12,log=print,verbose=True):
    return ProductAgentOrchestrator(model=model,reviewer=reviewer,candidate_limit=candidate_limit,
        log=log,verbose=verbose).run(product_source_id=product_source_id,apply=apply)
