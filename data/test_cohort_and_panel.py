import json
from pathlib import Path
from data.generate_seed import generate_cohort


def test_panel_genes_metadata():
    panel_file = Path(__file__).resolve().parent.parent / "engine" / "panel_genes.json"
    assert panel_file.exists(), "panel_genes.json must exist"
    
    with open(panel_file, "r", encoding="utf-8") as f:
        genes = json.load(f)

    assert len(genes) >= 10, "Should contain at least 10 key screening genes"
    for g in genes:
        assert "gene" in g
        assert g["inheritance"] in ("AR", "XL")
        assert "condition_name_en" in g
        assert "condition_name_ar" in g
        assert "severity_class" in g
        assert "source" in g
        assert "OMIM" not in g["source"], "Must avoid OMIM due to licensing"


def test_synthetic_cohort_structure():
    cohort = generate_cohort(seed=123)
    people = cohort["people"]
    couples = cohort["couples"]
    variants = cohort["variant_calls"]

    assert len(people) == 200, "Must contain exactly 200 people"
    assert len(couples) == 80, "Must contain exactly 80 couples"

    # Edge cases check
    minors = [p for p in people if (2026 - p["dob_year"]) < 18]
    assert len(minors) >= 1, "Must include minors under 18"

    pregnant = [p for p in people if p["pregnancy_status"]]
    assert len(pregnant) >= 1, "Must include pregnant individuals"

    xlinked_females = [v for v in variants if v["inheritance"] == "XL" and v["zygosity"] == "heterozygous"]
    assert len(xlinked_females) >= 1, "Must include X-linked female carriers"

    xlinked_males = [v for v in variants if v["inheritance"] == "XL" and v["zygosity"] == "hemizygous"]
    assert len(xlinked_males) >= 1, "Must include X-linked males"

    vus_variants = [v for v in variants if v["classification"] == "VUS"]
    assert len(vus_variants) >= 1, "Must include VUS cases"

    same_gene_matches = [c for c in couples if c["id"] == "cpl_link_001"]
    assert len(same_gene_matches) == 1, "Must include same gene match (Fatima & Tariq)"
