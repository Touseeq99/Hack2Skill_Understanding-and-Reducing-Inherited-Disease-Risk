"""Data models for deterministic risk engine."""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class VariantCall(BaseModel):
    """Genetic variant call from screening panel."""
    gene: str
    hgvs: str
    zygosity: Literal["heterozygous", "homozygous", "hemizygous"]
    classification: Literal["pathogenic", "likely_pathogenic", "VUS", "benign", "likely_benign"]
    inheritance: Literal["AR", "XL"]

    def is_pathogenic(self) -> bool:
        return self.classification in ("pathogenic", "likely_pathogenic")

    def is_vus(self) -> bool:
        return self.classification == "VUS"

    def is_benign(self) -> bool:
        return self.classification in ("benign", "likely_benign")


class PersonInput(BaseModel):
    """Input representation of a screened individual."""
    id: str
    sex: Literal["F", "M"]
    variants: List[VariantCall] = Field(default_factory=list)
    pregnancy_status: bool = False
    symptoms_reported: bool = False
    distress_signal: bool = False
    is_tested: bool = True
    partner_status: Optional[str] = None  # "untested", "negative", "different_gene", "same_gene"


class IconArrayData(BaseModel):
    """Visual icon array representation for risk communication."""
    total: int
    categories: List[Dict[str, Any]]


class PersonResult(BaseModel):
    """Deterministic individual risk classification result."""
    person_id: str
    category: Literal["screen_negative", "carrier", "xlinked_carrier", "xlinked_male", "possible_affected", "uncertain"]
    tier: Literal["T0", "T1", "T2", "T3"]
    rule_id: str
    genes: List[str]
    core_message_en: str
    core_message_ar: str
    natural_frequency: str
    icon_array: Dict[str, Any]
    rule_version: str = "v1"
    clinical_signoff: str = "DRAFT - requires clinical sign-off"


class CoupleResult(BaseModel):
    """Deterministic couple compatibility result. Guaranteed symmetric: couple(a, b) == couple(b, a)."""
    outcome: Literal["same_gene_match", "no_shared_gene", "uncertain_match", "incomplete", "xlinked_risk"]
    tier: Literal["T0", "T1", "T2", "T3"]
    rule_id: str
    shared_genes: List[str]
    natural_frequencies: Dict[str, str]
    icon_array: Dict[str, Any]
    core_message_en: str
    core_message_ar: str
    consanguinity_statement: Optional[Dict[str, Any]] = None
    rule_version: str = "v1"
    clinical_signoff: str = "DRAFT - requires clinical sign-off"

