"""One-off migration: move legacy plaintext variant details into the encrypted payload.

Usage:  python -m data.encrypt_variants        (idempotent; take a copy of the database first)
"""

from backend.database import db
from backend.vault import REDACTED, open_variant, store_variant


def main() -> int:
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, result_id, gene, hgvs, zygosity, classification, inheritance, encrypted_payload FROM variant_call")
    rows = cur.fetchall()
    moved = 0
    for r in rows:
        if r["gene"] == REDACTED:
            continue
        store_variant(cur, r["id"], r["result_id"], open_variant(r))
        moved += 1
    conn.commit()
    conn.close()
    print(f"Encrypted {moved} legacy variant rows ({len(rows) - moved} already protected).")
    return moved


if __name__ == "__main__":
    main()
