"""FHIR result ingestion (PDF section 1: results land in the vault first, never directly in the app).

Accepts a FHIR R4 `Bundle` containing one `DiagnosticReport` (subject = Patient/<person_id>) and
`Observation` resources with genomics-style components (LOINC):
  48018-6  gene studied              -> gene symbol
  81290-9  genomic DNA change (HGVS) -> HGVS string
  53034-5  allelic state             -> heterozygous / homozygous / hemizygous
  53037-8  clinical significance     -> pathogenic / likely pathogenic / VUS / (likely) benign

Benign and likely-benign calls are dropped at ingestion. Genes outside the screening panel are rejected.
This is a prototype mapping for synthetic data; a production integration (Malaffi / lab agreements) needs
the lab's actual profile and the clinical partner's sign-off.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from backend.vault import store_variant
from engine.models import VariantCall

LOINC = {"gene": "48018-6", "hgvs": "81290-9", "zygosity": "53034-5", "significance": "53037-8"}
_PANEL = {g["gene"]: g for g in json.loads((Path(__file__).resolve().parent.parent / "engine" / "panel_genes.json").read_text(encoding="utf-8"))}

_SIGNIFICANCE = {
    "pathogenic": "pathogenic", "la6668-3": "pathogenic",
    "likely pathogenic": "likely_pathogenic", "likely_pathogenic": "likely_pathogenic", "la26332-9": "likely_pathogenic",
    "uncertain significance": "VUS", "vus": "VUS", "la26333-7": "VUS",
    "likely benign": "likely_benign", "likely_benign": "likely_benign", "la26334-5": "likely_benign",
    "benign": "benign", "la6675-8": "benign",
}
_ZYGOSITY = {"heterozygous": "heterozygous", "la6706-1": "heterozygous", "homozygous": "homozygous", "la6705-3": "homozygous",
             "hemizygous": "hemizygous", "la6707-9": "hemizygous"}


def _text(component: Dict[str, Any]) -> str:
    if "valueString" in component:
        return str(component["valueString"]).strip()
    coding = (component.get("valueCodeableConcept") or {}).get("coding") or [{}]
    return str(coding[0].get("display") or coding[0].get("code") or "").strip()


def _code_of(component: Dict[str, Any]) -> str:
    for c in (component.get("code") or {}).get("coding", []):
        if c.get("code"):
            return c["code"]
    return ""


def parse_bundle(bundle: Dict[str, Any]) -> Tuple[str, str, str, List[VariantCall], int]:
    """Return (person_id, lab_id, fhir_ref, variants, dropped_benign_count). Raises 422 on invalid input."""
    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(status_code=422, detail="Expected a FHIR Bundle.")
    resources = [e.get("resource", {}) for e in bundle.get("entry", [])]
    reports = [r for r in resources if r.get("resourceType") == "DiagnosticReport"]
    if len(reports) != 1:
        raise HTTPException(status_code=422, detail="Bundle must contain exactly one DiagnosticReport.")
    report = reports[0]
    subject = (report.get("subject") or {}).get("reference", "")
    if not subject.startswith("Patient/"):
        raise HTTPException(status_code=422, detail="DiagnosticReport.subject must be Patient/<id>.")
    person_id = subject.split("/", 1)[1]
    lab_id = ((report.get("performer") or [{}])[0].get("reference") or "Organization/unknown").split("/", 1)[-1]
    fhir_ref = f"DiagnosticReport/{report.get('id') or hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()[:16]}"

    variants: List[VariantCall] = []
    dropped = 0
    errors: List[str] = []
    for i, obs in enumerate(r for r in resources if r.get("resourceType") == "Observation"):
        parts = {_code_of(c): _text(c) for c in obs.get("component", [])}
        gene, hgvs = parts.get(LOINC["gene"], ""), parts.get(LOINC["hgvs"], "")
        zyg = _ZYGOSITY.get(parts.get(LOINC["zygosity"], "").lower())
        sig = _SIGNIFICANCE.get(parts.get(LOINC["significance"], "").lower())
        if gene not in _PANEL:
            errors.append(f"Observation {i}: gene '{gene}' is not on the screening panel")
            continue
        if not hgvs or not zyg or not sig:
            errors.append(f"Observation {i}: missing or unrecognised HGVS, allelic state or significance")
            continue
        if sig in ("benign", "likely_benign"):
            dropped += 1  # benign / likely benign are dropped at ingestion
            continue
        variants.append(VariantCall(gene=gene, hgvs=hgvs, zygosity=zyg, classification=sig, inheritance=_PANEL[gene]["inheritance"]))
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    return person_id, lab_id, fhir_ref, variants, dropped


def ingest_bundle(db, audit, bundle: Dict[str, Any], actor: str) -> Dict[str, Any]:
    person_id, lab_id, fhir_ref, variants, dropped = parse_bundle(bundle)
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM person WHERE id = ?", (person_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Patient not found.")
    cur.execute("SELECT 1 FROM screening_result WHERE fhir_ref = ?", (fhir_ref,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="This DiagnosticReport was already ingested.")
    result_id = "scr_fhir_" + hashlib.sha256(fhir_ref.encode()).hexdigest()[:12]
    cur.execute(
        "INSERT INTO screening_result (id, person_id, panel_id, lab_id, fhir_ref, status) VALUES (?, ?, 'panel_uae_comprehensive_v1', ?, ?, 'received')",
        (result_id, person_id, lab_id, fhir_ref),
    )
    for n, v in enumerate(variants, 1):
        store_variant(cur, f"var_{result_id}_{n}", result_id, v)
    conn.commit()
    conn.close()
    audit.record_event(actor=actor, action="fhir_result_ingested", target=f"result:{result_id}")
    return {
        "result_id": result_id, "person_id": person_id, "variants_stored": len(variants), "benign_dropped": dropped,
        # Push notifications never carry result content.
        "notification": "Your result is ready",
    }
