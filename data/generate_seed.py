"""Synthetic data generator for Inherited Disease Risk Platform.
Produces 200 diverse individuals and 80 couples across clinical edge cases:
- Same-gene AR carrier couples
- VUS only cases
- X-linked female carriers
- X-linked hemizygous males
- Possible affected (homozygous or compound heterozygous in AR gene)
- Untested partner cases
- Minor cases (< 18 years old)
- Pregnant cases
- Screen negative individuals
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Any
from backend.database import Database
from backend.encryptor import default_encryptor
from backend.vault import store_variant
from engine.models import VariantCall

PANEL_GENES_FILE = Path(__file__).resolve().parent.parent / "engine" / "panel_genes.json"

FIRST_NAMES_FEMALE = [
    "Fatima", "Maryam", "Aisha", "Noor", "Shamma", "Moza", "Hessa", "Reem", "Salama",
    "Hind", "Latifa", "Maha", "Khadija", "Zainab", "Sara", "Amna", "Mira", "Dana",
    "Lulwa", "Meera", "Alyazia", "Maitha", "Mouza", "Rawdha", "Hamda", "Asma"
]

FIRST_NAMES_MALE = [
    "Tariq", "Mohammed", "Sultan", "Rashid", "Hamad", "Saeed", "Zayed", "Ahmed",
    "Mansoor", "Khalid", "Abdullah", "Omar", "Majid", "Salem", "Saif", "Nasser",
    "Fahad", "Ali", "Humaid", "Butti", "Obaid", "Khalfan", "Mubarak", "Ebraheem"
]

FAMILY_NAMES = [
    "Al Mansoori", "Al Mazrouei", "Al Zaabi", "Al Nuaimi", "Al Shamsi", "Al Dhaheri",
    "Al Suwaidi", "Al Qubaisi", "Al Falasi", "Al Marzooqi", "Al Kaabi", "Al Remeithi",
    "Al Ketbi", "Al Mehairbi", "Al Ameri", "Al Romaithi", "Al Nahyan", "Al Maktoum"
]

VARIANT_CATALOG = {
    "HBB": [
        {"hgvs": "c.93-21G>A", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
        {"hgvs": "c.118C>T", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
        {"hgvs": "c.79G>A", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
        {"hgvs": "c.315+1G>A", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
        {"hgvs": "c.20A>T", "zygosity": "heterozygous", "classification": "likely_pathogenic", "inheritance": "AR"},
        {"hgvs": "c.45C>T", "zygosity": "heterozygous", "classification": "VUS", "inheritance": "AR"},
    ],
    "HBA1": [
        {"hgvs": "c.95+2_95+6delTGAGG", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
        {"hgvs": "c.427T>C", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
    ],
    "CFTR": [
        {"hgvs": "c.1521_1523delCTT (p.Phe508del)", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
        {"hgvs": "c.1624G>T", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
        {"hgvs": "c.2988+1G>A", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
        {"hgvs": "c.1210-12[5]", "zygosity": "heterozygous", "classification": "VUS", "inheritance": "AR"},
    ],
    "SMN1": [
        {"hgvs": "c.840C>T (exon 7 deletion)", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
        {"hgvs": "c.835-44_840del", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
    ],
    "G6PD": [
        {"hgvs": "c.563C>T (Mediterranean)", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "XL"},
        {"hgvs": "c.202G>A (A-)", "zygosity": "hemizygous", "classification": "pathogenic", "inheritance": "XL"},
    ],
    "DMD": [
        {"hgvs": "c.583C>T (p.Arg195Ter)", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "XL"},
        {"hgvs": "c.10108C>T", "zygosity": "hemizygous", "classification": "pathogenic", "inheritance": "XL"},
        {"hgvs": "c.4238A>G", "zygosity": "heterozygous", "classification": "VUS", "inheritance": "XL"},
    ],
    "F8": [
        {"hgvs": "c.1241A>G", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "XL"},
        {"hgvs": "c.6046C>T", "zygosity": "hemizygous", "classification": "pathogenic", "inheritance": "XL"},
    ],
    "PAH": [
        {"hgvs": "c.1066-11G>A", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
        {"hgvs": "c.1222C>T", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
    ],
    "GJB2": [
        {"hgvs": "c.35delG", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
    ],
    "MEFV": [
        {"hgvs": "c.2080A>G (p.Met694Val)", "zygosity": "heterozygous", "classification": "pathogenic", "inheritance": "AR"},
    ]
}


def generate_cohort(seed: int = 42) -> Dict[str, Any]:
    """Generate deterministic synthetic cohort with exactly 200 people and 80 couples."""
    random.seed(seed)

    people: List[Dict[str, Any]] = []
    screening_results: List[Dict[str, Any]] = []
    variant_calls: List[Dict[str, Any]] = []
    couples: List[Dict[str, Any]] = []
    grants: List[Dict[str, Any]] = []

    # Current reference year is 2026
    current_year = 2026

    # 1. Generate 200 Persons
    for i in range(200):
        person_id = f"person_{i+1:03d}"
        sex = "F" if i < 100 else "M"
        first = random.choice(FIRST_NAMES_FEMALE if sex == "F" else FIRST_NAMES_MALE)
        last = random.choice(FAMILY_NAMES)
        name = f"{first} {last}"
        
        # Demographics & edge cases:
        # 5 minors (age < 18, dob_year >= 2009)
        if i in (10, 25, 50, 110, 140):
            dob_year = current_year - random.randint(15, 17)
        else:
            dob_year = current_year - random.randint(19, 45)

        # 12 pregnant females
        pregnancy_status = (sex == "F" and i in (2, 3, 7, 12, 18, 22, 30, 45, 60, 75, 88, 95))
        
        # Language & literacy
        language = "ar" if random.random() < 0.8 else "en"
        literacy_pref = random.choices(["standard", "simple", "audio"], weights=[0.6, 0.25, 0.15])[0]

        # Canonical demo couple keeps the names used in the demo script and the apps.
        name = {"person_001": "Fatima Al Mansoori", "person_101": "Tariq Al Mazrouei"}.get(person_id, name)

        person = {
            "id": person_id,
            "auth_id": f"auth_{person_id}",
            "name": name,
            "language": language,
            "literacy_pref": literacy_pref,
            "dob_year": dob_year,
            "sex": sex,
            "pregnancy_status": pregnancy_status,
            "created_at": "2026-11-01T08:00:00Z"
        }
        people.append(person)

    # 2. Pair 80 couples (Female 0..79 with Male 100..179)
    # Couple 0: Fatima (person_001) & Tariq (person_101) - Canonical Demo Couple (Same-gene HBB match)
    # Couple 1: Pregnant same-gene match (person_002 & person_102) -> T3 triage
    # Couple 2: Person 003 is homozygous/compound het HBB (Possible Affected) & Tariq-2
    # Couple 3: Untested partner (person_004 tested, partner_b person_104 untested)
    # Couple 4: X-linked female carrier (DMD) + male
    # Couple 5: X-linked male (G6PD/F8) + female
    # Couple 6: Carrier + VUS in same gene
    # Couple 7: Carrier + Different gene carrier (No shared gene)
    # Couple 8: Carrier + Negative
    # Couple 9: Both Negative

    for c_idx in range(80):
        link_id = f"cpl_link_{c_idx+1:03d}"
        p_a = people[c_idx]["id"]
        p_b = people[100 + c_idx]["id"]
        
        # Consanguinity: about 35% reported related
        is_consanguineous = (c_idx % 3 == 0)

        # Couple status & mutual consent variations:
        # Most couples active with mutual grants; some pending or revoked for testing
        if c_idx == 15:
            # Revoked grant
            status = "revoked"
            grant_a_active = False
            grant_b_active = True
        elif c_idx == 20:
            # One-sided grant (partner B hasn't granted)
            status = "pending"
            grant_a_active = True
            grant_b_active = False
        else:
            status = "active"
            grant_a_active = True
            grant_b_active = True

        couples.append({
            "id": link_id,
            "partner_a": p_a,
            "partner_b": p_b,
            "status": status,
            "is_consanguineous": is_consanguineous,
            "created_at": "2026-11-02T09:00:00Z",
            "revoked_at": "2026-11-05T14:00:00Z" if status == "revoked" else None
        })

        if grant_a_active:
            grants.append({
                "id": f"grant_{p_a}_{link_id}",
                "grantor": p_a,
                "grantee": p_b,
                "scope": "couple_result",
                "purpose": "Pre-marital genetic compatibility screening",
                "expires_at": "2027-11-02T09:00:00Z",
                "revoked_at": None
            })
        if grant_b_active:
            grants.append({
                "id": f"grant_{p_b}_{link_id}",
                "grantor": p_b,
                "grantee": p_a,
                "scope": "couple_result",
                "purpose": "Pre-marital genetic compatibility screening",
                "expires_at": "2027-11-02T09:00:00Z",
                "revoked_at": None if status != "revoked" else "2026-11-05T14:00:00Z"
            })

    # 3. Assign Screening Results and Variant Calls
    for p in people:
        pid = p["id"]
        p_num = int(pid.split("_")[1])

        # Person 104 is deliberately untested partner for Couple 3
        if pid == "person_104":
            continue

        result_id = f"scr_{pid}"
        screening_results.append({
            "id": result_id,
            "person_id": pid,
            "panel_id": "panel_uae_comprehensive_v1",
            "lab_id": "lab_abudhabi_genomics_01",
            "received_at": "2026-11-03T10:00:00Z",
            "fhir_ref": f"DiagnosticReport/{result_id}",
            "status": "processed"
        })

        # Specific Clinical Assignment
        # Canonical Couple 0: Fatima (person_001) & Tariq (person_101) -> HBB Pathogenic carriers
        if pid == "person_001":
            # Fatima: HBB carrier (c.93-21G>A)
            v = VARIANT_CATALOG["HBB"][0]
            enc_payload = default_encryptor.encrypt(f"{v['hgvs']} in HBB", f"var_{result_id}_1")
            variant_calls.append({
                "id": f"var_{result_id}_1",
                "result_id": result_id,
                "gene": "HBB",
                "hgvs": v["hgvs"],
                "zygosity": v["zygosity"],
                "classification": v["classification"],
                "inheritance": v["inheritance"],
                "encrypted_payload": enc_payload
            })
        elif pid == "person_101":
            # Tariq: HBB carrier (c.118C>T)
            v = VARIANT_CATALOG["HBB"][1]
            enc_payload = default_encryptor.encrypt(f"{v['hgvs']} in HBB", f"var_{result_id}_1")
            variant_calls.append({
                "id": f"var_{result_id}_1",
                "result_id": result_id,
                "gene": "HBB",
                "hgvs": v["hgvs"],
                "zygosity": v["zygosity"],
                "classification": v["classification"],
                "inheritance": v["inheritance"],
                "encrypted_payload": enc_payload
            })
        elif pid in ("person_002", "person_102"):
            # Couple 1: Both CFTR carriers (and person_002 is pregnant -> T3)
            v = VARIANT_CATALOG["CFTR"][0]
            enc_payload = default_encryptor.encrypt(f"{v['hgvs']} in CFTR", f"var_{result_id}_1")
            variant_calls.append({
                "id": f"var_{result_id}_1",
                "result_id": result_id,
                "gene": "CFTR",
                "hgvs": v["hgvs"],
                "zygosity": v["zygosity"],
                "classification": v["classification"],
                "inheritance": v["inheritance"],
                "encrypted_payload": enc_payload
            })
        elif pid == "person_003":
            # Possible affected: homozygous or compound het in AR gene (HBB)
            v1 = VARIANT_CATALOG["HBB"][0]
            v2 = VARIANT_CATALOG["HBB"][1]
            enc1 = default_encryptor.encrypt(f"{v1['hgvs']}", f"var_{result_id}_1")
            enc2 = default_encryptor.encrypt(f"{v2['hgvs']}", f"var_{result_id}_2")
            variant_calls.append({
                "id": f"var_{result_id}_1", "result_id": result_id, "gene": "HBB",
                "hgvs": v1["hgvs"], "zygosity": "heterozygous", "classification": "pathogenic",
                "inheritance": "AR", "encrypted_payload": enc1
            })
            variant_calls.append({
                "id": f"var_{result_id}_2", "result_id": result_id, "gene": "HBB",
                "hgvs": v2["hgvs"], "zygosity": "heterozygous", "classification": "pathogenic",
                "inheritance": "AR", "encrypted_payload": enc2
            })
        elif pid == "person_005":
            # X-linked carrier female (DMD)
            v = VARIANT_CATALOG["DMD"][0]
            enc = default_encryptor.encrypt(f"{v['hgvs']}", f"var_{result_id}_1")
            variant_calls.append({
                "id": f"var_{result_id}_1", "result_id": result_id, "gene": "DMD",
                "hgvs": v["hgvs"], "zygosity": "heterozygous", "classification": "pathogenic",
                "inheritance": "XL", "encrypted_payload": enc
            })
        elif pid == "person_106":
            # X-linked male (G6PD hemizygous)
            v = VARIANT_CATALOG["G6PD"][1]
            enc = default_encryptor.encrypt(f"{v['hgvs']}", f"var_{result_id}_1")
            variant_calls.append({
                "id": f"var_{result_id}_1", "result_id": result_id, "gene": "G6PD",
                "hgvs": v["hgvs"], "zygosity": "hemizygous", "classification": "pathogenic",
                "inheritance": "XL", "encrypted_payload": enc
            })
        elif pid == "person_007":
            # VUS only in CFTR
            v = VARIANT_CATALOG["CFTR"][3]
            enc = default_encryptor.encrypt(f"{v['hgvs']}", f"var_{result_id}_1")
            variant_calls.append({
                "id": f"var_{result_id}_1", "result_id": result_id, "gene": "CFTR",
                "hgvs": v["hgvs"], "zygosity": "heterozygous", "classification": "VUS",
                "inheritance": "AR", "encrypted_payload": enc
            })
        elif pid == "person_107":
            # Partner carries pathogenic CFTR variant -> Carrier + VUS in same gene
            v = VARIANT_CATALOG["CFTR"][1]
            enc = default_encryptor.encrypt(f"{v['hgvs']}", f"var_{result_id}_1")
            variant_calls.append({
                "id": f"var_{result_id}_1", "result_id": result_id, "gene": "CFTR",
                "hgvs": v["hgvs"], "zygosity": "heterozygous", "classification": "pathogenic",
                "inheritance": "AR", "encrypted_payload": enc
            })
        elif p_num % 4 == 0:
            # Single carrier of PAH
            v = VARIANT_CATALOG["PAH"][0]
            enc = default_encryptor.encrypt(f"{v['hgvs']}", f"var_{result_id}_1")
            variant_calls.append({
                "id": f"var_{result_id}_1", "result_id": result_id, "gene": "PAH",
                "hgvs": v["hgvs"], "zygosity": "heterozygous", "classification": "pathogenic",
                "inheritance": "AR", "encrypted_payload": enc
            })
        elif p_num % 7 == 0:
            # VUS only in HBB
            v = VARIANT_CATALOG["HBB"][5]
            enc = default_encryptor.encrypt(f"{v['hgvs']}", f"var_{result_id}_1")
            variant_calls.append({
                "id": f"var_{result_id}_1", "result_id": result_id, "gene": "HBB",
                "hgvs": v["hgvs"], "zygosity": "heterozygous", "classification": "VUS",
                "inheritance": "AR", "encrypted_payload": enc
            })
        # Otherwise: screen negative (no P/LP or VUS variants)

    return {
        "people": people,
        "couples": couples,
        "screening_results": screening_results,
        "variant_calls": variant_calls,
        "consent_grants": grants
    }


def seed_database(db: Database, cohort: Dict[str, Any]):
    """Insert cohort into database tables."""
    conn = db.get_connection()
    cur = conn.cursor()

    for p in cohort["people"]:
        cur.execute("""
            INSERT OR REPLACE INTO person (id, auth_id, name, language, literacy_pref, dob_year, sex, pregnancy_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (p["id"], p["auth_id"], p["name"], p["language"], p["literacy_pref"], p["dob_year"], p["sex"], int(p["pregnancy_status"]), p["created_at"]))

    for c in cohort["couples"]:
        cur.execute("""
            INSERT OR REPLACE INTO couple_link (id, partner_a, partner_b, status, created_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (c["id"], c["partner_a"], c["partner_b"], c["status"], c["created_at"], c.get("revoked_at")))

    for g in cohort["consent_grants"]:
        cur.execute("""
            INSERT OR REPLACE INTO consent_grant (id, grantor, grantee, scope, purpose, expires_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (g["id"], g["grantor"], g["grantee"], g["scope"], g["purpose"], g["expires_at"], g.get("revoked_at")))

    for r in cohort["screening_results"]:
        cur.execute("""
            INSERT OR REPLACE INTO screening_result (id, person_id, panel_id, lab_id, received_at, fhir_ref, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (r["id"], r["person_id"], r["panel_id"], r["lab_id"], r["received_at"], r["fhir_ref"], r["status"]))

    for v in cohort["variant_calls"]:
        store_variant(cur, v["id"], v["result_id"], VariantCall(
            gene=v["gene"], hgvs=v["hgvs"], zygosity=v["zygosity"],
            classification=v["classification"], inheritance=v["inheritance"]))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    cohort_data = generate_cohort()
    out_file = Path(__file__).resolve().parent / "synthetic_cohort.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(cohort_data, f, indent=2, ensure_ascii=False)
    print(f"Generated synthetic cohort saved to {out_file}:")
    print(f"- People: {len(cohort_data['people'])}")
    print(f"- Couples: {len(cohort_data['couples'])}")
    print(f"- Screening Results: {len(cohort_data['screening_results'])}")
    print(f"- Variant Calls: {len(cohort_data['variant_calls'])}")
    print(f"- Consent Grants: {len(cohort_data['consent_grants'])}")

    # Seed local database
    local_db = Database()
    seed_database(local_db, cohort_data)
    print("Successfully seeded local database!")
