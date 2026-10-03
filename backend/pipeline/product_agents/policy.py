from __future__ import annotations
import copy
from .schemas import FinalDecision
from .repository import SUPPORTED, clean

RELATIONS = {'ITEM':'HAS_ITEM','MATERIAL':'HAS_MATERIAL','COLOR':'HAS_COLOR','STYLE':'HAS_STYLE','TPO':'HAS_TPO'}
DETAIL_RELATIONS = {k: 'HAS_'+k for k in ('FIT','SILHOUETTE','NECKLINE','SLEEVE','LENGTH','SHAPE')}
GENDERS = {'MEN','WOMEN','UNISEX','MALE','FEMALE','M','W','U','A','BOTH','ALL'}


def blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple)):
        return not value or all(blank(v) for v in value)
    if isinstance(value, dict):
        return not value or all(blank(v) for v in value.values())
    return False


def check_evidence(evidence, context):
    text = context['evidence_sources'].get(evidence.path)
    return bool(text is not None and evidence.quote.strip() and evidence.quote in text)


def expected_relation(term):
    if term['term_type'] == 'DETAIL':
        return DETAIL_RELATIONS.get(term.get('detail_attribute_type'), 'HAS_DETAIL')
    return RELATIONS.get(term['term_type'])


def validate_changes(context, name, attributes, terms):
    source = context['source']
    accepted = {'fields':{}, 'attributes':{}, 'remove_term_ids':[], 'add_terms':[], 'rejected':[]}
    def reject(kind, value, reason):
        accepted['rejected'].append(dict(kind=kind, proposal=value.model_dump(), reason=reason))
    used_fields = set()
    for patch in name.patches:
        if patch.field in used_fields:
            raise ValueError('Duplicate field proposals')
        used_fields.add(patch.field)
        if patch.confidence != 'HIGH' or not check_evidence(patch.evidence, context):
            reject('field', patch, 'HIGH confidence and exact source evidence required')
            continue
        value = patch.value.strip()
        if not value:
            reject('field',patch,'Empty replacement forbidden')
            continue
        if patch.field != 'normalized_name' and not blank(source[patch.field]):
            reject('field',patch,'Existing field preserved')
            continue
        if patch.field == 'season_year':
            if not value.isdigit() or not 1900 <= int(value) <= 2100:
                reject('field',patch,'Invalid season year')
                continue
            value = int(value)
        elif len(value) > {'normalized_name':500,'style_no':255,'gender_scope':50,'season':50}[patch.field]:
            reject('field',patch,'Field length exceeded')
            continue
        if patch.field == 'gender_scope' and value.upper() not in GENDERS:
            reject('field',patch,'Unrecognized gender value')
            continue
        if source[patch.field] != value:
            accepted['fields'][patch.field] = value
    attrs = source['attributes']
    if not isinstance(attrs, dict):
        raise ValueError('ProductSource.attributes must be an object')
    normalized = attrs.get('normalized')
    if normalized is None:
        normalized = {}
    if not isinstance(normalized, dict):
        raise ValueError('attributes.normalized must be an object')
    used_keys = set()
    for patch in attributes.patches:
        if patch.key in used_keys:
            raise ValueError('Duplicate attribute proposals')
        used_keys.add(patch.key)
        if not blank(normalized.get(patch.key)):
            reject('attribute',patch,'Existing normalized attribute preserved')
            continue
        # Existing mapped terms cannot be used as the only evidence for extraction.
        if patch.confidence != 'HIGH' or not check_evidence(patch.evidence,context):
            reject('attribute',patch,'HIGH confidence and exact source evidence required')
            continue
        values = list(dict.fromkeys(v.strip() for v in patch.values if v.strip()))
        if not values or len(values) > 50 or any(len(v)>500 for v in values):
            reject('attribute',patch,'Invalid attribute values')
            continue
        accepted['attributes'][patch.key] = values
    links = {t['product_term_id']:t for t in source['terms']}
    for removal in terms.removals:
        if removal.product_term_id not in links:
            raise ValueError('Term removal does not belong to this ProductSource')
        if removal.confidence != 'HIGH' or not check_evidence(removal.evidence,context):
            reject('term_removal',removal,'HIGH confidence and exact source evidence required')
            continue
        accepted['remove_term_ids'].append(removal.product_term_id)
    catalog = {t['term_id']:t for t in context['catalog']}
    for addition in terms.additions:
        term = catalog.get(addition.term_id)
        if term is None or term['status'] != 'ACTIVE' or expected_relation(term) != addition.relation_type:
            raise ValueError('Term addition has invalid ID/status/relation')
        if addition.confidence != 'HIGH' or not check_evidence(addition.evidence,context):
            reject('term_addition',addition,'HIGH confidence and exact source evidence required')
            continue
        accepted['add_terms'].append(dict(term_id=addition.term_id,relation_type=addition.relation_type))
    return accepted


def preview_source(context, changes):
    source = copy.deepcopy(context['source'])
    source.update(changes['fields'])
    normalized = source['attributes'].setdefault('normalized', {})
    if normalized is None:
        normalized = source['attributes']['normalized'] = {}
    normalized.update(changes['attributes'])
    source['terms'] = [t for t in source['terms'] if t['product_term_id'] not in changes['remove_term_ids']]
    catalog = {t['term_id']:t for t in context['catalog']}
    for addition in changes['add_terms']:
        source['terms'].append(dict(product_term_id=None, **catalog[addition['term_id']], relation_type=addition['relation_type']))
    return source


def gate(context, identity, *, issues=()):
    source = context['source']
    def decision(action, reason, pid=None):
        return FinalDecision(action=action, product_id=pid, confidence='HIGH', reasons=[reason])
    if source['product_id'] is not None:
        return decision('KEEP','Existing Product link preserved',source['product_id'])
    if source['source_code'] not in SUPPORTED or source['status'] != 'ACTIVE':
        return decision('HOLD','Unsupported source or inactive ProductSource')
    if not source['brand_id'] or source['brand_mapping_status'] == 'EXCLUDED' or source.get('brand_status') != 'ACTIVE':
        return decision('HOLD','FEEDIT brand missing or excluded')
    ids = {p['product_id'] for p in context['candidates']}
    assessment_ids = [a.product_id for a in identity.assessments]
    if set(assessment_ids) != ids or len(assessment_ids) != len(ids):
        return decision('HOLD','Identity reviewer did not assess the exact candidate set')
    if issues or identity.conflicts:
        return decision('HOLD','Review found unresolved issues/conflicts')
    same = [a for a in identity.assessments if a.verdict=='SAME']
    uncertain = [a for a in identity.assessments if a.verdict=='UNCERTAIN' or a.conflicts or a.confidence!='HIGH']
    if len(same)==1 and same[0].confidence=='HIGH' and not uncertain:
        pid = same[0].product_id
        if source['source_code']=='musinsa_used' and pid not in context['exact_style_product_ids']:
            return decision('HOLD','USED requires an original style_no exact candidate')
        return decision('MAP','One high confidence identical Product; no unresolved candidates',pid)
    if same or uncertain:
        return decision('HOLD','Ambiguous or uncertain existing Product identity')
    if source['source_code']=='musinsa_used':
        return decision('HOLD','USED-only Product promotion disabled')
    if identity.distinct_product and identity.confidence=='HIGH' and not blank(source['source_name'] or source['normalized_name']):
        return decision('PROMOTE','Distinct Product confirmed; musinsa/kream receive promotion priority')
    return decision('HOLD','Insufficient evidence for mapping or promotion')


def reconcile(gated, proposed):
    # Final reviewer may veto; it may never escalate beyond deterministic gate.
    if gated.action == 'KEEP':
        return gated
    if proposed.action == 'HOLD':
        return FinalDecision(action='HOLD',product_id=None,confidence=proposed.confidence,reasons=proposed.reasons)
    if proposed.confidence != 'HIGH' or proposed.action != gated.action or proposed.product_id != gated.product_id:
        return FinalDecision(action='HOLD',product_id=None,confidence='HIGH',reasons=['Final review disagrees with validated policy'])
    return proposed
