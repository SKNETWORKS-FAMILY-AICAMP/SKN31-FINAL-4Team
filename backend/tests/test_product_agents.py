"""SQLite integration checks against field definitions extracted from supplied models.
Run: python -m unittest discover -s tests -v (from this archive's root).
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'/'fixtures'))
from django.conf import settings
settings.configure(INSTALLED_APPS=['apps.core'],DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':str(ROOT/'tests'/'test.sqlite3')}},USE_TZ=True,SECRET_KEY='test-only',DEFAULT_AUTO_FIELD='django.db.models.BigAutoField')
import django
django.setup()
from django.apps import apps
from django.db import connection
from apps.core.models import Source, Brand, BrandSource, Product, ProductSource, ProductTerm, DictionaryTerm, Detail
from pipeline.product_agents import run_product_agent, run_product_agent_batch, apply_plan, StaleAgentPlan
from pipeline.product_agents.schemas import NameReview, AttributeReview, TermReview, IdentityReview, FinalDecision, Evidence, FieldPatch, AttributePatch, TermRemoval, TermAddition, CandidateAssessment
from pipeline.product_agents.repository import load_context

# SQLite cannot address PostgreSQL schema-qualified names. Field definitions stay unchanged.
for model in apps.get_models(include_auto_created=True):
    model._meta.db_table = model._meta.db_table.replace('"','').replace('.','_')
if Path(settings.DATABASES['default']['NAME']).exists():
    Path(settings.DATABASES['default']['NAME']).unlink()
with connection.schema_editor() as editor:
    for model in apps.get_models():
        editor.create_model(model)

class FakeReviewer:
    def __init__(self, name=None, attrs=None, terms=None, identity=None, veto=False, fail=None):
        self.name=name or NameReview(patches=[],issues=[])
        self.attrs=attrs or AttributeReview(patches=[],issues=[])
        self.terms=terms or TermReview(removals=[],additions=[],issues=[])
        self.identity=identity
        self.veto=veto
        self.fail=fail
    def review(self, *, role, prompt, payload, schema):
        if role==self.fail:
            raise RuntimeError('Simulated API refusal/timeout')
        if role=='name': return self.name
        if role=='attributes': return self.attrs
        if role=='terms': return self.terms
        if role=='identity':
            return self.identity or IdentityReview(
                assessments=[CandidateAssessment(product_id=p['product_id'],verdict='DIFFERENT',confidence='HIGH',reasons=['different item'],conflicts=[]) for p in payload['candidates']],
                distinct_product=True,confidence='HIGH',reasons=['new item'],conflicts=[])
        if self.veto:
            return FinalDecision(action='HOLD',product_id=None,confidence='HIGH',reasons=['manual review'])
        return FinalDecision.model_validate(payload['deterministic_gate'])

class Integration(unittest.TestCase):
    def setUp(self):
        # ORM delete preserves relationships; source created per test.
        for model in [ProductTerm,ProductSource,Product,BrandSource,Detail,DictionaryTerm,Brand,Source]:
            model.objects.all().delete()
        self.brand=Brand.objects.create(brand_code='BRAND_TEST',name='테스트')
        self.source=Source.objects.create(code='musinsa',name='무신사',source_type='COMMERCE')
        self.bs=BrandSource.objects.create(brand=self.brand,source=self.source,source_brand_id='brand',mapping_status='AUTO_MAPPED')
        self.ps=ProductSource.objects.create(source=self.source,source_brand=self.bs,source_product_id='1',source_name='백포인트 원피스 여성',style_no='DRESS-1',attributes={'raw':{'gender':'여성'},'normalized':{}},market_type='RETAIL')
    def run_agent(self, reviewer=None, apply=True):
        return run_product_agent(product_source_id=self.ps.pk,reviewer=reviewer or FakeReviewer(),apply=apply,log=lambda _:None)
    def test_promotion_identity_and_raw_preserved(self):
        result=self.run_agent()
        self.ps.refresh_from_db()
        p=Product.objects.get(pk=result['product_id'])
        self.assertEqual(result['action'],'PROMOTE')
        self.assertTrue(p.product_code.startswith('FEEDIT_'))
        self.assertNotEqual(p.product_code,self.ps.style_no)
        self.assertEqual(self.ps.source_name,'백포인트 원피스 여성')
        self.assertEqual(self.ps.mapping_status,'MAPPED')
        self.assertIn('_feedit_product_agent',self.ps.attributes)
    def test_existing_link_is_kept_and_idempotent_plan(self):
        first=self.run_agent()
        replay=apply_plan(plan=first['plan'])
        self.assertEqual(replay['status'],'ALREADY_APPLIED')
        second=self.run_agent()
        self.assertEqual(second['action'],'KEEP')
        self.assertEqual(Product.objects.count(),1)
    def test_wrong_term_removal_fill_and_name(self):
        bag=DictionaryTerm.objects.create(term_type='ITEM',canonical_name='가방')
        link=ProductTerm.objects.create(product_source=self.ps,term=bag,relation_type='HAS_ITEM')
        ev=Evidence(path='source_name',quote='백포인트 원피스 여성',explanation='백 means back detail; dress')
        reviewer=FakeReviewer(
            name=NameReview(patches=[FieldPatch(field='normalized_name',value='백포인트 원피스',confidence='HIGH',evidence=ev),FieldPatch(field='gender_scope',value='WOMEN',confidence='HIGH',evidence=ev)],issues=[]),
            attrs=AttributeReview(patches=[AttributePatch(key='gender',values=['WOMEN'],confidence='HIGH',evidence=ev)],issues=[]),
            terms=TermReview(removals=[TermRemoval(product_term_id=link.pk,confidence='HIGH',evidence=ev)],additions=[],issues=[]))
        self.run_agent(reviewer)
        self.ps.refresh_from_db()
        self.assertFalse(ProductTerm.objects.filter(pk=link.pk).exists())
        self.assertTrue(DictionaryTerm.objects.filter(pk=bag.pk).exists())
        self.assertEqual(self.ps.normalized_name,'백포인트 원피스')
        self.assertEqual(self.ps.attributes['normalized']['gender'],['WOMEN'])
        self.assertEqual(self.ps.gender_scope,'WOMEN')
    def test_only_fill_empty_and_reject_fake_evidence(self):
        self.ps.gender_scope='MEN'
        self.ps.attributes['normalized']={'material':['울']}
        self.ps.save()
        ev=Evidence(path='source_name',quote='여성',explanation='explicit')
        fake=Evidence(path='source_name',quote='폴리에스터 100%',explanation='invented')
        reviewer=FakeReviewer(name=NameReview(patches=[FieldPatch(field='gender_scope',value='WOMEN',confidence='HIGH',evidence=ev)],issues=[]),
           attrs=AttributeReview(patches=[AttributePatch(key='material',values=['폴리에스터'],confidence='HIGH',evidence=fake),AttributePatch(key='fit',values=['레귤러'],confidence='HIGH',evidence=fake)],issues=[]))
        result=self.run_agent(reviewer)
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.gender_scope,'MEN')
        self.assertEqual(self.ps.attributes['normalized']['material'],['울'])
        self.assertNotIn('fit',self.ps.attributes['normalized'])
        self.assertEqual(len(result['changes']['rejected']),3)
    def make_candidate(self, style='DRESS-1'):
        p=Product.objects.create(brand=self.brand,canonical_name='원피스',normalized_name='원피스')
        ProductSource.objects.create(source=self.source,source_brand=self.bs,source_product_id=f'candidate-{p.pk}',product=p,source_name='원피스',style_no=style)
        return p
    def test_map_one_existing_candidate(self):
        p=self.make_candidate()
        identity=IdentityReview(assessments=[CandidateAssessment(product_id=p.pk,verdict='SAME',confidence='HIGH',reasons=['style+item'],conflicts=[])],distinct_product=False,confidence='HIGH',reasons=['same'],conflicts=[])
        result=self.run_agent(FakeReviewer(identity=identity))
        self.assertEqual(result['action'],'MAP')
        self.assertEqual(result['product_id'],p.pk)
        self.assertEqual(Product.objects.count(),1)
    def test_multiple_same_is_hold(self):
        candidates=[self.make_candidate(),self.make_candidate()]
        identity=IdentityReview(assessments=[CandidateAssessment(product_id=p.pk,verdict='SAME',confidence='HIGH',reasons=['style'],conflicts=[]) for p in candidates],distinct_product=False,confidence='HIGH',reasons=['same code'],conflicts=[])
        result=self.run_agent(FakeReviewer(identity=identity))
        self.assertEqual(result['action'],'HOLD')
        self.assertEqual(Product.objects.count(),2)
    def test_used_no_promotion_and_name_only_no_mapping(self):
        self.source.code='musinsa_used';self.source.save()
        self.assertEqual(self.run_agent()['action'],'HOLD')
        p=self.make_candidate(style='OTHER')
        identity=IdentityReview(assessments=[CandidateAssessment(product_id=p.pk,verdict='SAME',confidence='HIGH',reasons=['name'],conflicts=[])],distinct_product=False,confidence='HIGH',reasons=['same'],conflicts=[])
        self.assertEqual(self.run_agent(FakeReviewer(identity=identity))['action'],'HOLD')
    def test_stale_source_or_candidate_rejected(self):
        planned=self.run_agent(apply=False)
        self.ps.source_name='다른 상품';self.ps.save()
        with self.assertRaises(StaleAgentPlan): apply_plan(plan=planned['plan'])
        self.assertEqual(Product.objects.count(),0)
        planned=self.run_agent(apply=False)
        self.make_candidate()
        with self.assertRaises(StaleAgentPlan): apply_plan(plan=planned['plan'])
    def test_refusal_does_not_write(self):
        with self.assertRaises(RuntimeError): self.run_agent(FakeReviewer(fail='terms'))
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.attributes,{'raw':{'gender':'여성'},'normalized':{}})
        self.assertEqual(Product.objects.count(),0)
    def test_final_veto(self):
        self.assertEqual(self.run_agent(FakeReviewer(veto=True))['action'],'HOLD')
        self.assertEqual(Product.objects.count(),0)
    def test_missing_brand_hold(self):
        self.bs.brand=None;self.bs.save()
        self.assertEqual(self.run_agent()['action'],'HOLD')
    def test_kream_promotes_and_preserves_resale(self):
        self.source.code='kream';self.source.save()
        self.ps.market_type='RESALE';self.ps.save()
        self.assertEqual(self.run_agent()['action'],'PROMOTE')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.market_type,'RESALE')
    def test_transaction_rolls_back_term_delete_and_creation(self):
        bag=DictionaryTerm.objects.create(term_type='ITEM',canonical_name='가방')
        link=ProductTerm.objects.create(product_source=self.ps,term=bag,relation_type='HAS_ITEM')
        ev=Evidence(path='source_name',quote='백포인트 원피스',explanation='wrong bag')
        reviewer=FakeReviewer(terms=TermReview(removals=[TermRemoval(product_term_id=link.pk,confidence='HIGH',evidence=ev)],additions=[],issues=[]))
        plan=self.run_agent(reviewer,apply=False)['plan']
        with patch.object(ProductSource,'save',side_effect=RuntimeError('save failed')):
            with self.assertRaises(RuntimeError): apply_plan(plan=plan)
        self.assertTrue(ProductTerm.objects.filter(pk=link.pk).exists())
        self.assertEqual(Product.objects.count(),0)
    def test_relation_validation(self):
        term=DictionaryTerm.objects.create(term_type='DETAIL',canonical_name='하프기장')
        Detail.objects.create(term=term,attribute_type='LENGTH')
        self.ps.source_name='하프기장 원피스';self.ps.save()
        ev=Evidence(path='source_name',quote='하프기장',explanation='length')
        reviewer=FakeReviewer(terms=TermReview(removals=[],additions=[TermAddition(term_id=term.pk,relation_type='HAS_LENGTH',confidence='HIGH',evidence=ev)],issues=[]))
        self.run_agent(reviewer)
        self.assertTrue(ProductTerm.objects.filter(product_source=self.ps,term=term,relation_type='HAS_LENGTH').exists())
    def test_foreign_term_removal_rejected(self):
        reviewer=FakeReviewer(terms=TermReview(removals=[TermRemoval(product_term_id=99999,confidence='HIGH',evidence=Evidence(path='source_name',quote='원피스',explanation='wrong'))],additions=[],issues=[]))
        with self.assertRaises(ValueError): self.run_agent(reviewer)
        self.assertEqual(Product.objects.count(),0)
    def test_batch_limit_and_resume_priority(self):
        # Lower-ID Zigzag comes after Musinsa because anchors are processed first.
        zig=Source.objects.create(code='zigzag',name='지그재그',source_type='COMMERCE')
        zbs=BrandSource.objects.create(source=zig,brand=self.brand,source_brand_id='z')
        other=ProductSource.objects.create(source=zig,source_brand=zbs,source_product_id='z',source_name='다른 치마')
        r1=run_product_agent_batch(max_products=1,reviewer=FakeReviewer(),apply=True,log=lambda _:None)
        self.assertEqual(r1['attempted_products'],1)
        self.assertEqual(r1['results'][0]['product_source_id'],self.ps.pk)
        self.assertTrue(r1['has_more'])
        r2=run_product_agent_batch(max_products=1,cursor=r1['next_cursor'],reviewer=FakeReviewer(),apply=True,log=lambda _:None)
        self.assertEqual(r2['results'][0]['product_source_id'],other.pk)
        self.assertFalse(r2['has_more'])
    def test_batch_failures_visible_and_cursor_advances(self):
        result=run_product_agent_batch(max_products=1,reviewer=FakeReviewer(fail='name'),apply=True,log=lambda _:None)
        self.assertEqual(result['failed_product_source_ids'],[self.ps.pk])
        self.assertEqual(result['next_cursor']['after_brand_id'],self.brand.pk)
        self.assertEqual(Product.objects.count(),0)

if __name__=='__main__': unittest.main()
