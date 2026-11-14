# Clinical Rules Catalog (Version v1)

> **Status**: DRAFT - requires clinical sign-off  
> **Source**: `engine/rules/v1.yaml`  
> **Effective Date**: 2026-11-14  

This catalog specifies the deterministic rules for individual variant interpretation and couple compatibility matching. No artificial intelligence or probabilistic randomness is permitted in risk classification or numerical frequency generation.

---

## Individual Classification Rules (IND)

| Rule ID | Category | Default Tier | Clinical Condition | Core Clinical Message (EN) | Natural Frequency |
|---|---|---|---|---|---|
| **IND-001** | `screen_negative` | **T0** | No P/LP variants found on screening panel | No carrier changes found for the conditions tested. This lowers but does not remove risk. | Lower than average population risk |
| **IND-002** | `carrier` | **T1** (untested partner)<br>**T0** (partner negative/diff)<br>**T2** (partner same gene) | Exactly one P/LP variant in an autosomal recessive (AR) gene | You carry one changed copy of a gene. Carriers are usually healthy. It matters if a partner carries the same gene. | 1 in 1 carrier status (healthy carrier) |
| **IND-003** | `xlinked_carrier` | **T2** | One P/LP variant in an X-linked (XL) gene in a female | You carry an X-linked gene variant. Each son has a 1 in 2 chance of being affected; each daughter has a 1 in 2 chance of being a carrier. | Sons: 1 in 2 affected; Daughters: 1 in 2 carrier |
| **IND-004** | `xlinked_male` | **T2** | P/LP variant in an X-linked (XL) gene in a male (hemizygous) | You have an X-linked gene variant on your single X chromosome. All daughters will be carriers; sons will not inherit this variant. | Daughters: 1 in 1 carrier; Sons: 0 in 1 unaffected |
| **IND-005** | `possible_affected` | **T2** (default)<br>**T3** (if pregnant/symptoms/distress) | Two P/LP variants in the same AR gene (homozygous or compound heterozygous) | Two genetic changes were found in the same gene. This is not a carrier result and needs clinical review. | Clinical review required (not carrier) |
| **IND-006** | `uncertain` | **T0** (default)<br>**T2** (if partner has P/LP in same gene) | Only variant(s) of uncertain significance (VUS) found; no P/LP | A change of unknown meaning was found. It is not treated as a carrier result. | Uncertain clinical meaning |

---

## Couple Compatibility Rules (CPL)

All couple compatibility operations are strictly symmetric: `couple(a, b) == couple(b, a)`.

| Rule ID | Couple Outcome | Tier | Partner A & B Genotypes | Per-Pregnancy Numbers Shown | Icon Array Structure |
|---|---|---|---|---|---|
| **CPL-001** | `same_gene_match` | **T2** | Both carriers of same AR gene | **1 in 4 affected, 1 in 2 carrier, 1 in 4 neither** | 1 red, 2 orange, 1 green (total 4) |
| **CPL-002** | `same_gene_match` | **T2** | Possible affected + carrier of same AR gene | **1 in 2 affected, 1 in 2 carrier** | 2 red, 2 orange (total 4) |
| **CPL-003** | `same_gene_match` | **T2** | Both possible affected in same AR gene | **All children affected (4 in 4)** | 4 red (total 4) |
| **CPL-004** | `no_shared_gene` | **T0** | Carrier gene X + Carrier different gene Y | Residual risk from panel sensitivity (approx. 1 in 100 to 1 in 200) | 99 green, 1 gray (total 100) |
| **CPL-005** | `no_shared_gene` | **T0** | Carrier + Negative partner | Residual risk from panel sensitivity (approx. 1 in 400 to 1 in 800) | 99 green, 1 gray (total 100) |
| **CPL-006** | `uncertain_match` | **T2** | Carrier gene X + VUS in gene X | **NO number shown**; explained as clinically uncertain | 100 purple (total 100) |
| **CPL-007** | `incomplete` | **T1** | One partner tested; other partner untested/unlinked | Partner invite requires explicit permission | 1 gray pending |
| **CPL-008** | `xlinked_risk` | **T2** | Female X-linked carrier + Any partner | **Sons: 1 in 2 affected; Daughters: 1 in 2 carrier** | Split per sex of child |
| **CPL-009** | `xlinked_risk` | **T2** | Male X-linked + Any partner | **Sons: 0 affected; Daughters: 1 in 1 carrier** | Split per sex of child |
| **CPL-010** | `no_shared_gene` | **T0** | Both screened negative | Standard baseline population residual risk | 98 green, 2 gray (total 100) |

---

## Consanguinity Background Statement (CNS-001)

- **Clinical Grounding**: Bennett et al., NSGC 2002 guidelines on consanguineous unions.
- **Framing**: Neutral, culturally respectful, non-stigmatising, and strictly non-attributive. Cousin marriage is recognized as a common, valued cultural tradition with zero blame.
- **Numbers Side-by-Side**:
  - General Population: **About 96 to 97 in 100** have no major birth condition (3-4% baseline defect risk).
  - First Cousins: **About 94 to 96 in 100** have no major birth condition (roughly 1.7 to 2.8 percentage points above baseline).
- **Critical Clarification**: Explicitly presented as **general birth condition risk**, NOT recessive condition risk alone.

