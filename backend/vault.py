"""Genetic payload vault: variant details are stored ONLY inside the AES-256-GCM encrypted payload.

The plaintext columns of `variant_call` hold a redaction marker, so a database dump (or a SQL injection
that reads the table) does not reveal genes, HGVS names, zygosity or classification. The engine receives
decrypted `VariantCall` objects in memory only. Legacy rows (plaintext columns, non-JSON payload) are still
readable so old databases keep working until `python -m data.encrypt_variants` is run.
"""

import json
from typing import List

from backend.encryptor import default_encryptor
from engine.models import VariantCall

REDACTED = "[encrypted]"


def seal_variant(variant_id: str, v: VariantCall) -> str:
    payload = json.dumps({
        "gene": v.gene, "hgvs": v.hgvs, "zygosity": v.zygosity,
        "classification": v.classification, "inheritance": v.inheritance,
    })
    return default_encryptor.encrypt(payload, variant_id)


def store_variant(cur, variant_id: str, result_id: str, v: VariantCall) -> None:
    """Insert (or replace) a variant with only the encrypted payload carrying clinical content."""
    cur.execute(
        """
        INSERT OR REPLACE INTO variant_call (id, result_id, gene, hgvs, zygosity, classification, inheritance, encrypted_payload)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (variant_id, result_id, REDACTED, REDACTED, REDACTED, REDACTED, REDACTED, seal_variant(variant_id, v)),
    )


def open_variant(row) -> VariantCall:
    """Decrypt a variant_call row; fall back to plaintext columns for legacy rows."""
    try:
        data = json.loads(default_encryptor.decrypt(row["encrypted_payload"], row["id"]))
        if isinstance(data, dict) and "gene" in data:
            return VariantCall(**data)
    except Exception:
        pass  # legacy row: payload was a plain summary string
    return VariantCall(
        gene=row["gene"], hgvs=row["hgvs"], zygosity=row["zygosity"],
        classification=row["classification"], inheritance=row["inheritance"],
    )


def load_variants(cur, person_id: str) -> List[VariantCall]:
    cur.execute(
        """
        SELECT vc.id, vc.gene, vc.hgvs, vc.zygosity, vc.classification, vc.inheritance, vc.encrypted_payload
        FROM variant_call vc JOIN screening_result sr ON vc.result_id = sr.id
        WHERE sr.person_id = ?
        """,
        (person_id,),
    )
    return [open_variant(r) for r in cur.fetchall()]
