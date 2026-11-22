# 06 Item master

The official Caltrans item list, item families, and how bid items map to it.

| File | Rows | What it is |
| --- | --- | --- |
| `item_master.csv` | 2,634 | Every item code: description, pay unit, family, spec section, final-pay flag, whether it is on the 2026 list, and successors of a retired code |
| `item_families.csv` | 75 | Which 2026 Standard Specifications section belongs to which item family |
| `item_mapping.csv` | 100 | The 100 in-scope items: family, whether the code is current, and how many bid rows and contracts use it |
| `item_master_report.md` | | Mapping rate, the unmapped code, and family totals |

**How it was produced:** step 1.4 read the Caltrans 2026 Bid Items list (numerical XLSX, revised 10-19-26) from https://dot.ca.gov/programs/design/2026-ccs-standard-plans-and-standard-specifications. Units follow each code's 2026 pay unit, retired codes are kept and flagged, and families follow the 2026 Standard Specifications sections.
