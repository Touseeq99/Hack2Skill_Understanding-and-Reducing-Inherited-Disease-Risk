import pytest
from engine.models import VariantCall, PersonInput
from engine.risk_engine import classify


def test_ind_001_screen_negative():
    # No variants at all
    p1 = PersonInput(id="p1", sex="F", variants=[])
    res = classify(p1)
    assert res.category == "screen_negative"
    assert res.rule_id == "IND-001"
    assert res.tier == "T0"
    assert "lowers but does not remove" in res.core_message_en

    # Only benign / likely_benign variants -> dropped at ingestion
    p2 = PersonInput(id="p2", sex="M", variants=[
        VariantCall(gene="HBB", hgvs="c.9T>C", zygosity="heterozygous", classification="benign", inheritance="AR"),
        VariantCall(gene="CFTR", hgvs="c.10A>G", zygosity="heterozygous", classification="likely_benign", inheritance="AR"),
    ])
    res2 = classify(p2)
    assert res2.category == "screen_negative"
    assert res2.rule_id == "IND-001"
    assert res2.tier == "T0"


def test_ind_002_carrier():
    # Single AR pathogenic variant, default partner_status is None -> T1
    p1 = PersonInput(id="p1", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    res = classify(p1)
    assert res.category == "carrier"
    assert res.rule_id == "IND-002"
    assert res.tier == "T1"
    assert res.genes == ["HBB"]

    # Partner negative or diff gene -> T0
    p1.partner_status = "negative"
    assert classify(p1).tier == "T0"
    p1.partner_status = "different_gene"
    assert classify(p1).tier == "T0"

    # Partner same gene -> T2
    p1.partner_status = "same_gene"
    assert classify(p1).tier == "T2"


def test_ind_003_xlinked_carrier_female():
    p = PersonInput(id="p_f", sex="F", variants=[
        VariantCall(gene="DMD", hgvs="c.583C>T", zygosity="heterozygous", classification="pathogenic", inheritance="XL")
    ])
    res = classify(p)
    assert res.category == "xlinked_carrier"
    assert res.rule_id == "IND-003"
    assert res.tier == "T2"
    assert "Each son has a 1 in 2" in res.core_message_en


def test_ind_004_xlinked_male():
    p = PersonInput(id="p_m", sex="M", variants=[
        VariantCall(gene="G6PD", hgvs="c.202G>A", zygosity="hemizygous", classification="pathogenic", inheritance="XL")
    ])
    res = classify(p)
    assert res.category == "xlinked_male"
    assert res.rule_id == "IND-004"
    assert res.tier == "T2"
    assert "single X chromosome" in res.core_message_en


def test_ind_005_possible_affected():
    # Compound heterozygous: 2 distinct pathogenic variants in same AR gene
    p_comp = PersonInput(id="p_comp", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="heterozygous", classification="pathogenic", inheritance="AR"),
        VariantCall(gene="HBB", hgvs="c.118C>T", zygosity="heterozygous", classification="likely_pathogenic", inheritance="AR"),
    ])
    res = classify(p_comp)
    assert res.category == "possible_affected"
    assert res.rule_id == "IND-005"
    assert res.tier == "T2"  # default T2

    # Escalates to T3 if pregnant, distress signal, or symptoms
    p_comp.pregnancy_status = True
    assert classify(p_comp).tier == "T3"

    p_comp.pregnancy_status = False
    p_comp.distress_signal = True
    assert classify(p_comp).tier == "T3"

    p_comp.distress_signal = False
    p_comp.symptoms_reported = True
    assert classify(p_comp).tier == "T3"

    # Homozygous single variant (counts as 2 copies)
    p_homo = PersonInput(id="p_homo", sex="M", variants=[
        VariantCall(gene="CFTR", hgvs="c.1521_1523delCTT", zygosity="homozygous", classification="pathogenic", inheritance="AR")
    ])
    res_homo = classify(p_homo)
    assert res_homo.category == "possible_affected"
    assert res_homo.tier == "T2"


def test_ind_006_uncertain_vus_only():
    p = PersonInput(id="p_vus", sex="M", variants=[
        VariantCall(gene="HBB", hgvs="c.45C>T", zygosity="heterozygous", classification="VUS", inheritance="AR")
    ])
    res = classify(p)
    assert res.category == "uncertain"
    assert res.rule_id == "IND-006"
    assert res.tier == "T0"
    assert "not treated as a carrier result" in res.core_message_en

    # If partner has P/LP in the same gene -> T2
    p.partner_status = "same_gene_plp"
    assert classify(p).tier == "T2"


def test_invalid_rule_version_raises():
    p = PersonInput(id="p_test", sex="F", variants=[])
    with pytest.raises(FileNotFoundError):
        classify(p, rule_version="v_invalid_999")
