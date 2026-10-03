from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    _usage: dict = PrivateAttr(default_factory=dict)

class Evidence(StrictModel):
    path: str
    quote: str
    explanation: str

class FieldPatch(StrictModel):
    field: Literal['normalized_name', 'style_no', 'gender_scope', 'season_year', 'season']
    value: str
    confidence: Literal['HIGH', 'MEDIUM', 'LOW']
    evidence: Evidence

class AttributePatch(StrictModel):
    key: Literal['item','material','color','fit','silhouette','neckline','sleeve','length','shape','detail','style','tpo','gender','season','size','production_type','pattern']
    values: list[str]
    confidence: Literal['HIGH', 'MEDIUM', 'LOW']
    evidence: Evidence

class TermRemoval(StrictModel):
    product_term_id: int
    confidence: Literal['HIGH', 'MEDIUM', 'LOW']
    evidence: Evidence

class TermAddition(StrictModel):
    term_id: int
    relation_type: str
    confidence: Literal['HIGH', 'MEDIUM', 'LOW']
    evidence: Evidence

class NameReview(StrictModel):
    patches: list[FieldPatch]
    issues: list[str]

class AttributeReview(StrictModel):
    patches: list[AttributePatch]
    issues: list[str]

class TermReview(StrictModel):
    removals: list[TermRemoval]
    additions: list[TermAddition]
    issues: list[str]

class CandidateAssessment(StrictModel):
    product_id: int
    verdict: Literal['SAME', 'DIFFERENT', 'UNCERTAIN']
    confidence: Literal['HIGH','MEDIUM','LOW']
    reasons: list[str]
    conflicts: list[str]

class IdentityReview(StrictModel):
    assessments: list[CandidateAssessment]
    distinct_product: bool
    confidence: Literal['HIGH','MEDIUM','LOW']
    reasons: list[str]
    conflicts: list[str]

class FinalDecision(StrictModel):
    action: Literal['MAP', 'PROMOTE', 'HOLD', 'KEEP']
    product_id: int | None
    confidence: Literal['HIGH','MEDIUM','LOW']
    reasons: list[str]

class AgentPlan(StrictModel):
    product_source_id: int
    candidate_limit: int
    snapshot_hash: str
    candidate_universe_hash: str
    name_review: NameReview
    attribute_review: AttributeReview
    term_review: TermReview
    identity_review: IdentityReview
    decision: FinalDecision
