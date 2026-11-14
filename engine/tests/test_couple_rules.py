from engine.models import VariantCall, PersonInput
from engine.risk_engine import couple


def test_cpl_001_both_carriers_same_ar_gene():
    f = PersonInput(id="f", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    m = PersonInput(id="m", sex="M", variants=[
        VariantCall(gene="HBB", hgvs="c.118C>T", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    res = couple(f, m)
    assert res.outcome == "same_gene_match"
    assert res.rule_id == "CPL-001"
    assert res.tier == "T2"
    assert res.shared_genes == ["HBB"]
    assert res.natural_frequencies["affected"] == "1 in 4"
    assert res.natural_frequencies["carrier"] == "1 in 2"
    assert res.natural_frequencies["unaffected_non_carrier"] == "1 in 4"
    assert res.icon_array["total"] == 4


def test_cpl_002_affected_plus_carrier_same_ar_gene():
    # Affected (2 variants) + Carrier (1 variant)
    p_aff = PersonInput(id="p_aff", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="heterozygous", classification="pathogenic", inheritance="AR"),
        VariantCall(gene="HBB", hgvs="c.118C>T", zygosity="heterozygous", classification="pathogenic", inheritance="AR"),
    ])
    p_car = PersonInput(id="p_car", sex="M", variants=[
        VariantCall(gene="HBB", hgvs="c.79G>A", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    res1 = couple(p_aff, p_car)
    res2 = couple(p_car, p_aff)
    assert res1.outcome == "same_gene_match"
    assert res1.rule_id == "CPL-002"
    assert res1.tier == "T2"
    assert res1.natural_frequencies["affected"] == "1 in 2"
    assert res1.natural_frequencies["carrier"] == "1 in 2"
    assert res1 == res2, "Must be symmetric"


def test_cpl_003_both_affected_same_ar_gene():
    p1 = PersonInput(id="p1", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="homozygous", classification="pathogenic", inheritance="AR")
    ])
    p2 = PersonInput(id="p2", sex="M", variants=[
        VariantCall(gene="HBB", hgvs="c.118C>T", zygosity="homozygous", classification="pathogenic", inheritance="AR")
    ])
    res = couple(p1, p2)
    assert res.outcome == "same_gene_match"
    assert res.rule_id == "CPL-003"
    assert res.tier == "T2"
    assert "all children" in res.natural_frequencies["affected"].lower() or "4 in 4" in res.natural_frequencies["affected"]


def test_cpl_004_different_ar_genes():
    p1 = PersonInput(id="p1", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    p2 = PersonInput(id="p2", sex="M", variants=[
        VariantCall(gene="CFTR", hgvs="c.1521_1523delCTT", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    res = couple(p1, p2)
    assert res.outcome == "no_shared_gene"
    assert res.rule_id == "CPL-004"
    assert res.tier == "T0"


def test_cpl_005_carrier_plus_negative():
    p_car = PersonInput(id="p_car", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    p_neg = PersonInput(id="p_neg", sex="M", variants=[])
    res = couple(p_car, p_neg, panel_sensitivity=0.95)
    assert res.outcome == "no_shared_gene"
    assert res.rule_id == "CPL-005"
    assert res.tier == "T0"
    assert "95%" in res.natural_frequencies["residual_risk"]


def test_cpl_006_carrier_plus_vus_same_gene():
    p_car = PersonInput(id="p_car", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    p_vus = PersonInput(id="p_vus", sex="M", variants=[
        VariantCall(gene="HBB", hgvs="c.45C>T", zygosity="heterozygous", classification="VUS", inheritance="AR")
    ])
    res = couple(p_car, p_vus)
    assert res.outcome == "uncertain_match"
    assert res.rule_id == "CPL-006"
    assert res.tier == "T2"
    assert "NO number shown" in res.natural_frequencies["note"]


def test_cpl_007_partner_not_tested():
    p1 = PersonInput(id="p1", sex="F", variants=[], is_tested=True)
    res_none = couple(p1, None)
    assert res_none.outcome == "incomplete"
    assert res_none.rule_id == "CPL-007"
    assert res_none.tier == "T1"

    p_untested = PersonInput(id="p_untested", sex="M", variants=[], is_tested=False)
    res_untested = couple(p1, p_untested)
    assert res_untested.outcome == "incomplete"
    assert res_untested.rule_id == "CPL-007"
    assert res_untested.tier == "T1"


def test_cpl_008_and_009_xlinked_risks():
    # Female X-linked carrier
    f_xl = PersonInput(id="f_xl", sex="F", variants=[
        VariantCall(gene="DMD", hgvs="c.583C>T", zygosity="heterozygous", classification="pathogenic", inheritance="XL")
    ])
    m_neg = PersonInput(id="m_neg", sex="M", variants=[])
    res_f = couple(f_xl, m_neg)
    assert res_f.outcome == "xlinked_risk"
    assert res_f.rule_id == "CPL-008"
    assert res_f.tier == "T2"
    assert "1 in 2" in res_f.natural_frequencies["sons_affected"]

    # Male X-linked hemizygous
    m_xl = PersonInput(id="m_xl", sex="M", variants=[
        VariantCall(gene="G6PD", hgvs="c.202G>A", zygosity="hemizygous", classification="pathogenic", inheritance="XL")
    ])
    f_neg = PersonInput(id="f_neg", sex="F", variants=[])
    res_m = couple(m_xl, f_neg)
    assert res_m.outcome == "xlinked_risk"
    assert res_m.rule_id == "CPL-009"
    assert res_m.tier == "T2"
    assert res_m.natural_frequencies["sons_affected"] == "0 (none affected)"


def test_cpl_010_both_negative():
    p1 = PersonInput(id="p1", sex="F", variants=[])
    p2 = PersonInput(id="p2", sex="M", variants=[])
    res = couple(p1, p2)
    assert res.outcome == "no_shared_gene"
    assert res.rule_id == "CPL-010"
    assert res.tier == "T0"


def test_consanguinity_statement_attached():
    p1 = PersonInput(id="p1", sex="F", variants=[])
    p2 = PersonInput(id="p2", sex="M", variants=[])
    
    # Without consanguinity
    res_standard = couple(p1, p2, is_consanguineous=False)
    assert res_standard.consanguinity_statement is None

    # With consanguinity
    res_cns = couple(p1, p2, is_consanguineous=True)
    assert res_cns.consanguinity_statement is not None
    assert res_cns.consanguinity_statement["rule_id"] == "CNS-001"
    assert "Bennett et al., NSGC 2002" in res_cns.consanguinity_statement["body_en"]
    # Check side-by-side numbers
    assert "96" in res_cns.consanguinity_statement["side_by_side"]["general_population"]
    assert "94" in res_cns.consanguinity_statement["side_by_side"]["first_cousins"]
