"""Property-based symmetry testing for couple compatibility engine.

Verifies the mathematical property:
couple(a, b) == couple(b, a)
across randomized genotypes, variant classifications, and genders.
"""

import random
from typing import List
from engine.models import VariantCall, PersonInput
from engine.risk_engine import couple

try:
    from hypothesis import given, strategies as st, settings
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

SAMPLE_GENES = ["HBB", "CFTR", "SMN1", "PAH", "DMD", "G6PD"]
CLASSIFICATIONS = ["pathogenic", "likely_pathogenic", "VUS", "benign"]
ZYGOSITIES = ["heterozygous", "homozygous", "hemizygous"]


def generate_random_person(person_id: str, rng: random.Random) -> PersonInput:
    sex = rng.choice(["F", "M"])
    num_vars = rng.randint(0, 3)
    variants: List[VariantCall] = []
    
    for i in range(num_vars):
        gene = rng.choice(SAMPLE_GENES)
        inheritance = "XL" if gene in ("DMD", "G6PD") else "AR"
        classification = rng.choice(CLASSIFICATIONS)
        if inheritance == "XL" and sex == "M":
            zygosity = "hemizygous"
        else:
            zygosity = rng.choice(["heterozygous", "homozygous"])
            
        variants.append(VariantCall(
            gene=gene,
            hgvs=f"c.{rng.randint(10, 2000)}A>G",
            zygosity=zygosity,
            classification=classification,
            inheritance=inheritance,
        ))

    is_tested = rng.choice([True, True, True, False])
    pregnancy = (sex == "F" and rng.choice([True, False]))
    
    return PersonInput(
        id=person_id,
        sex=sex,
        variants=variants,
        pregnancy_status=pregnancy,
        is_tested=is_tested
    )


def test_couple_symmetry_randomized_trials():
    """Run 150 randomized trials to prove couple(a, b) == couple(b, a)."""
    rng = random.Random(42)
    for trial in range(150):
        p_a = generate_random_person(f"p_a_{trial}", rng)
        p_b = generate_random_person(f"p_b_{trial}", rng)
        is_cns = rng.choice([True, False])
        sens = rng.choice([0.90, 0.95, 0.99])

        res_ab = couple(p_a, p_b, is_consanguineous=is_cns, panel_sensitivity=sens)
        res_ba = couple(p_b, p_a, is_consanguineous=is_cns, panel_sensitivity=sens)

        assert res_ab.outcome == res_ba.outcome, f"Failed symmetry outcome on trial {trial}"
        assert res_ab.tier == res_ba.tier, f"Failed symmetry tier on trial {trial}"
        assert res_ab.rule_id == res_ba.rule_id, f"Failed symmetry rule_id on trial {trial}"
        assert sorted(res_ab.shared_genes) == sorted(res_ba.shared_genes)
        assert res_ab.natural_frequencies == res_ba.natural_frequencies
        assert res_ab.consanguinity_statement == res_ba.consanguinity_statement


if HAS_HYPOTHESIS:
    @given(st.integers(min_value=0, max_value=1000000))
    @settings(max_examples=50)
    def test_couple_symmetry_hypothesis(seed):
        rng = random.Random(seed)
        p_a = generate_random_person("p_a", rng)
        p_b = generate_random_person("p_b", rng)
        is_cns = rng.choice([True, False])
        
        res_ab = couple(p_a, p_b, is_consanguineous=is_cns)
        res_ba = couple(p_b, p_a, is_consanguineous=is_cns)

        assert res_ab == res_ba
