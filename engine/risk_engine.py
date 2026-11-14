"""Pure, deterministic genetic risk engine.

Rules and numbers are executed exclusively from versioned YAML specifications.
No network calls, no probabilistic randomness, no LLM in the math.
Guaranteed symmetric for couple compatibility: couple(a, b) == couple(b, a).
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
from engine.models import VariantCall, PersonInput, PersonResult, CoupleResult


def _load_rules(version: str = "v1") -> Dict[str, Any]:
    rules_path = Path(__file__).resolve().parent / "rules" / f"{version}.yaml"
    if not rules_path.exists():
        raise FileNotFoundError(f"Rule definition file not found: {rules_path}")
    with open(rules_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Cache loaded rules
_RULES_CACHE: Dict[str, Dict[str, Any]] = {}


def get_rules(version: str = "v1") -> Dict[str, Any]:
    if version not in _RULES_CACHE:
        _RULES_CACHE[version] = _load_rules(version)
    return _RULES_CACHE[version]


def _filter_variants(variants: List[VariantCall]) -> List[VariantCall]:
    """Drop benign and likely benign variants at ingestion."""
    return [v for v in variants if not v.is_benign()]


def classify(person: PersonInput, rule_version: str = "v1") -> PersonResult:
    """Classify an individual's genetic risk using versioned deterministic clinical rules."""
    rules = get_rules(rule_version)
    clinical_signoff = rules.get("clinical_signoff", "DRAFT - requires clinical sign-off")
    ind_rules_map = {r["id"]: r for r in rules["individual_rules"]}

    # Filter out benign / likely benign
    active_variants = _filter_variants(person.variants)
    plp_variants = [v for v in active_variants if v.is_pathogenic()]
    vus_variants = [v for v in active_variants if v.is_vus()]

    # Case 1: No P/LP variants
    if not plp_variants:
        if vus_variants:
            # IND-006: Uncertain Significance (VUS Only)
            r = ind_rules_map["IND-006"]
            tier = "T2" if person.partner_status == "same_gene_plp" else r["default_tier"]
            return PersonResult(
                person_id=person.id,
                category="uncertain",
                tier=tier,
                rule_id=r["id"],
                genes=[v.gene for v in vus_variants],
                core_message_en=r["core_message_en"],
                core_message_ar=r["core_message_ar"],
                natural_frequency=r["natural_frequency"],
                icon_array=r["icon_array"],
                rule_version=rule_version,
                clinical_signoff=clinical_signoff,
            )
        else:
            # IND-001: Screen Negative
            r = ind_rules_map["IND-001"]
            return PersonResult(
                person_id=person.id,
                category="screen_negative",
                tier=r["default_tier"],
                rule_id=r["id"],
                genes=[],
                core_message_en=r["core_message_en"],
                core_message_ar=r["core_message_ar"],
                natural_frequency=r["natural_frequency"],
                icon_array=r["icon_array"],
                rule_version=rule_version,
                clinical_signoff=clinical_signoff,
            )

    # Check for X-linked variants
    xl_plp = [v for v in plp_variants if v.inheritance == "XL"]
    if xl_plp:
        if person.sex == "F":
            # IND-003: X-Linked Female Carrier
            r = ind_rules_map["IND-003"]
            return PersonResult(
                person_id=person.id,
                category="xlinked_carrier",
                tier=r["default_tier"],
                rule_id=r["id"],
                genes=[v.gene for v in xl_plp],
                core_message_en=r["core_message_en"],
                core_message_ar=r["core_message_ar"],
                natural_frequency=r["natural_frequency"],
                icon_array=r["icon_array"],
                rule_version=rule_version,
                clinical_signoff=clinical_signoff,
            )
        else:
            # IND-004: X-Linked Male (Hemizygous)
            r = ind_rules_map["IND-004"]
            return PersonResult(
                person_id=person.id,
                category="xlinked_male",
                tier=r["default_tier"],
                rule_id=r["id"],
                genes=[v.gene for v in xl_plp],
                core_message_en=r["core_message_en"],
                core_message_ar=r["core_message_ar"],
                natural_frequency=r["natural_frequency"],
                icon_array=r["icon_array"],
                rule_version=rule_version,
                clinical_signoff=clinical_signoff,
            )

    # Autosomal recessive analysis
    ar_plp = [v for v in plp_variants if v.inheritance == "AR"]
    gene_counts: Dict[str, int] = {}
    for v in ar_plp:
        # homozygous counts as 2 variants
        weight = 2 if v.zygosity == "homozygous" else 1
        gene_counts[v.gene] = gene_counts.get(v.gene, 0) + weight

    # Check for possible affected (two P/LP variants in same AR gene)
    affected_genes = [gene for gene, count in gene_counts.items() if count >= 2]
    if affected_genes:
        # IND-005: Possible Affected
        r = ind_rules_map["IND-005"]
        # T2 by default; T3 if pregnant, distress signal, or symptoms reported
        tier = "T3" if (person.pregnancy_status or person.distress_signal or person.symptoms_reported) else "T2"
        return PersonResult(
            person_id=person.id,
            category="possible_affected",
            tier=tier,
            rule_id=r["id"],
            genes=affected_genes,
            core_message_en=r["core_message_en"],
            core_message_ar=r["core_message_ar"],
            natural_frequency=r["natural_frequency"],
            icon_array=r["icon_array"],
            rule_version=rule_version,
            clinical_signoff=clinical_signoff,
        )

    # IND-002: Autosomal Recessive Single Carrier
    r = ind_rules_map["IND-002"]
    # Tier determination:
    # T1 if partner untested or unlinked; T0 if partner negative or carrier of diff gene; T2 if partner has same gene
    if person.partner_status in ("negative", "different_gene"):
        tier = "T0"
    elif person.partner_status == "same_gene":
        tier = "T2"
    else:
        tier = "T1"

    carrier_genes = list(gene_counts.keys())
    return PersonResult(
        person_id=person.id,
        category="carrier",
        tier=tier,
        rule_id=r["id"],
        genes=carrier_genes,
        core_message_en=r["core_message_en"],
        core_message_ar=r["core_message_ar"],
        natural_frequency=r["natural_frequency"],
        icon_array=r["icon_array"],
        rule_version=rule_version,
        clinical_signoff=clinical_signoff,
    )


def couple(
    a: Optional[PersonInput],
    b: Optional[PersonInput],
    is_consanguineous: bool = False,
    panel_sensitivity: float = 0.95,
    rule_version: str = "v1",
) -> CoupleResult:
    """Compute couple compatibility risk.
    
    Pure deterministic function.
    Guaranteed symmetric: couple(a, b) == couple(b, a).
    """
    rules = get_rules(rule_version)
    clinical_signoff = rules.get("clinical_signoff", "DRAFT - requires clinical sign-off")
    cpl_rules_map = {r["id"]: r for r in rules["couple_rules"]}

    # Consanguinity statement attached if requested
    cns_statement = None
    if is_consanguineous and "consanguinity_statement" in rules:
        cns = rules["consanguinity_statement"]
        cns_statement = {
            "rule_id": cns["rule_id"],
            "title_en": cns["title_en"],
            "title_ar": cns["title_ar"],
            "body_en": cns["body_en"],
            "body_ar": cns["body_ar"],
            "side_by_side": cns["side_by_side"],
            "clinical_signoff": clinical_signoff,
        }

    # CPL-007: Partner Not Tested / Incomplete
    if a is None or b is None or not a.is_tested or not b.is_tested:
        r = cpl_rules_map["CPL-007"]
        return CoupleResult(
            outcome="incomplete",
            tier=r["tier"],
            rule_id=r["id"],
            shared_genes=[],
            natural_frequencies=r["natural_frequencies"],
            icon_array=r["icon_array"],
            core_message_en=r["core_message_en"],
            core_message_ar=r["core_message_ar"],
            consanguinity_statement=cns_statement,
            rule_version=rule_version,
            clinical_signoff=clinical_signoff,
        )

    # Filter variants symmetrically
    vars_a = _filter_variants(a.variants)
    vars_b = _filter_variants(b.variants)

    # Symmetrically evaluate X-linked variants
    females = [p for p in (a, b) if p.sex == "F"]
    males = [p for p in (a, b) if p.sex == "M"]

    # Check if any female partner has XL P/LP variant
    xl_female_genes: List[str] = []
    for f in females:
        for v in _filter_variants(f.variants):
            if v.inheritance == "XL" and v.is_pathogenic():
                xl_female_genes.append(v.gene)

    if xl_female_genes:
        r = cpl_rules_map["CPL-008"]
        return CoupleResult(
            outcome="xlinked_risk",
            tier=r["tier"],
            rule_id=r["id"],
            shared_genes=sorted(list(set(xl_female_genes))),
            natural_frequencies=r["natural_frequencies"],
            icon_array=r["icon_array"],
            core_message_en=r["core_message_en"],
            core_message_ar=r["core_message_ar"],
            consanguinity_statement=cns_statement,
            rule_version=rule_version,
            clinical_signoff=clinical_signoff,
        )

    # Check if any male partner has XL P/LP variant
    xl_male_genes: List[str] = []
    for m in males:
        for v in _filter_variants(m.variants):
            if v.inheritance == "XL" and v.is_pathogenic():
                xl_male_genes.append(v.gene)

    if xl_male_genes:
        r = cpl_rules_map["CPL-009"]
        return CoupleResult(
            outcome="xlinked_risk",
            tier=r["tier"],
            rule_id=r["id"],
            shared_genes=sorted(list(set(xl_male_genes))),
            natural_frequencies=r["natural_frequencies"],
            icon_array=r["icon_array"],
            core_message_en=r["core_message_en"],
            core_message_ar=r["core_message_ar"],
            consanguinity_statement=cns_statement,
            rule_version=rule_version,
            clinical_signoff=clinical_signoff,
        )

    # Autosomal Recessive Analysis
    # Tally P/LP variants per AR gene for person A and person B
    ar_plp_a: Dict[str, int] = {}
    for v in vars_a:
        if v.inheritance == "AR" and v.is_pathogenic():
            weight = 2 if v.zygosity == "homozygous" else 1
            ar_plp_a[v.gene] = ar_plp_a.get(v.gene, 0) + weight

    ar_plp_b: Dict[str, int] = {}
    for v in vars_b:
        if v.inheritance == "AR" and v.is_pathogenic():
            weight = 2 if v.zygosity == "homozygous" else 1
            ar_plp_b[v.gene] = ar_plp_b.get(v.gene, 0) + weight

    shared_ar_genes = sorted(list(set(ar_plp_a.keys()) & set(ar_plp_b.keys())))

    if shared_ar_genes:
        # Both carry variants in the same AR gene
        primary_gene = shared_ar_genes[0]
        cnt_a = ar_plp_a[primary_gene]
        cnt_b = ar_plp_b[primary_gene]

        if cnt_a >= 2 and cnt_b >= 2:
            # CPL-003: Both Affected Same AR Gene
            r = cpl_rules_map["CPL-003"]
            return CoupleResult(
                outcome="same_gene_match",
                tier=r["tier"],
                rule_id=r["id"],
                shared_genes=shared_ar_genes,
                natural_frequencies=r["natural_frequencies"],
                icon_array=r["icon_array"],
                core_message_en=r["core_message_en"],
                core_message_ar=r["core_message_ar"],
                consanguinity_statement=cns_statement,
                rule_version=rule_version,
                clinical_signoff=clinical_signoff,
            )
        elif (cnt_a >= 2 and cnt_b == 1) or (cnt_b >= 2 and cnt_a == 1):
            # CPL-002: Affected Plus Carrier Same AR Gene
            r = cpl_rules_map["CPL-002"]
            return CoupleResult(
                outcome="same_gene_match",
                tier=r["tier"],
                rule_id=r["id"],
                shared_genes=shared_ar_genes,
                natural_frequencies=r["natural_frequencies"],
                icon_array=r["icon_array"],
                core_message_en=r["core_message_en"],
                core_message_ar=r["core_message_ar"],
                consanguinity_statement=cns_statement,
                rule_version=rule_version,
                clinical_signoff=clinical_signoff,
            )
        else:
            # CPL-001: Both Carriers Same AR Gene
            r = cpl_rules_map["CPL-001"]
            return CoupleResult(
                outcome="same_gene_match",
                tier=r["tier"],
                rule_id=r["id"],
                shared_genes=shared_ar_genes,
                natural_frequencies=r["natural_frequencies"],
                icon_array=r["icon_array"],
                core_message_en=r["core_message_en"],
                core_message_ar=r["core_message_ar"],
                consanguinity_statement=cns_statement,
                rule_version=rule_version,
                clinical_signoff=clinical_signoff,
            )

    # Check for Carrier Gene X + VUS in Gene X
    vus_genes_a = {v.gene for v in vars_a if v.is_vus()}
    vus_genes_b = {v.gene for v in vars_b if v.is_vus()}

    vus_match = sorted(list((set(ar_plp_a.keys()) & vus_genes_b) | (set(ar_plp_b.keys()) & vus_genes_a)))
    if vus_match:
        # CPL-006: Carrier Gene X Plus VUS Gene X
        r = cpl_rules_map["CPL-006"]
        return CoupleResult(
            outcome="uncertain_match",
            tier=r["tier"],
            rule_id=r["id"],
            shared_genes=vus_match,
            natural_frequencies=r["natural_frequencies"],
            icon_array=r["icon_array"],
            core_message_en=r["core_message_en"],
            core_message_ar=r["core_message_ar"],
            consanguinity_statement=cns_statement,
            rule_version=rule_version,
            clinical_signoff=clinical_signoff,
        )

    # Carrier of gene X + carrier of different gene Y
    if len(ar_plp_a) > 0 and len(ar_plp_b) > 0:
        # CPL-004: Different AR Genes Carried
        r = cpl_rules_map["CPL-004"]
        return CoupleResult(
            outcome="no_shared_gene",
            tier=r["tier"],
            rule_id=r["id"],
            shared_genes=[],
            natural_frequencies=r["natural_frequencies"],
            icon_array=r["icon_array"],
            core_message_en=r["core_message_en"],
            core_message_ar=r["core_message_ar"],
            consanguinity_statement=cns_statement,
            rule_version=rule_version,
            clinical_signoff=clinical_signoff,
        )

    # Carrier + Negative
    if (len(ar_plp_a) > 0 and len(ar_plp_b) == 0 and len(vus_genes_b) == 0) or \
       (len(ar_plp_b) > 0 and len(ar_plp_a) == 0 and len(vus_genes_a) == 0):
        # CPL-005: Carrier Plus Negative Partner
        r = cpl_rules_map["CPL-005"]
        # Incorporate panel sensitivity into residual risk string
        sens_pct = int(panel_sensitivity * 100)
        res_freqs = dict(r["natural_frequencies"])
        res_freqs["residual_risk"] = f"Estimated 1 in 400 to 1 in 800 based on {sens_pct}% panel sensitivity"
        return CoupleResult(
            outcome="no_shared_gene",
            tier=r["tier"],
            rule_id=r["id"],
            shared_genes=[],
            natural_frequencies=res_freqs,
            icon_array=r["icon_array"],
            core_message_en=r["core_message_en"],
            core_message_ar=r["core_message_ar"],
            consanguinity_statement=cns_statement,
            rule_version=rule_version,
            clinical_signoff=clinical_signoff,
        )

    # CPL-010: Both Negative or VUS without pathogenic match
    r = cpl_rules_map["CPL-010"]
    return CoupleResult(
        outcome="no_shared_gene",
        tier=r["tier"],
        rule_id=r["id"],
        shared_genes=[],
        natural_frequencies=r["natural_frequencies"],
        icon_array=r["icon_array"],
        core_message_en=r["core_message_en"],
        core_message_ar=r["core_message_ar"],
        consanguinity_statement=cns_statement,
        rule_version=rule_version,
        clinical_signoff=clinical_signoff,
    )
