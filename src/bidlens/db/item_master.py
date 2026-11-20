"""Item master, unit normalization and item families (step 1.4).

Decisions: D-027 (source list), D-028 (units), D-029 (retired codes), D-030 (families).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import openpyxl

DEFAULT_ITEM_LIST = Path("data/raw/item_list/bid_items_10-19-2026_numerically.xlsx")

# D-030: 2026 Standard Specifications section -> item family.
_FAMILY_SECTIONS: dict[str, tuple[int, ...]] = {
    "General and Overhead": (*range(5, 12), 99),
    "Traffic Control": (12,),
    "Water Pollution and Site Management": (13,),
    "Environmental and Existing Facilities": (14, 15, 18),
    "Earthwork and Clearing": (16, 17, 19),
    "Landscape and Erosion Control": tuple(range(20, 25)),
    "Base and Subbase": tuple(range(25, 31)),
    "Asphalt Surfacing": tuple(range(36, 40)),
    "Concrete Pavement": (40, 41, 42),
    "Walls and Ground Support": (46, 47, 48, 58),
    "Piling": (49,),
    "Structural Concrete and Reinforcement": tuple(range(50, 55)),
    "Steel Structures, Signs and Painting": (55, 56, 57, 59),
    "Bridge Rehabilitation and Removal": (60,),
    "Drainage": tuple(range(61, 73)),
    "Minor Concrete and Miscellaneous": tuple(range(73, 79)),
    "Fencing, Guardrail and Barriers": tuple(range(80, 84)),
    "Striping and Markings": (84, 85),
    "Electrical and Signals": (86, 87),
}
SECTION_FAMILY = {s: fam for fam, secs in _FAMILY_SECTIONS.items() for s in secs}

# D-028: metric unit -> (US customary unit, quantity factor). Price divides by the factor.
UNIT_FACTORS: dict[str, tuple[str, float]] = {
    "M": ("LF", 3.28084),
    "M2": ("SQFT", 10.7639),
    "M3": ("CY", 1.30795),
    "KG": ("LB", 2.20462),
    "TONN": ("TON", 1.10231),
    "L": ("GAL", 0.264172),
    "HA": ("ACRE", 2.47105),
    "KM": ("MI", 0.621371),
}

# D-029: retired codes split by Caltrans into several successors.
RETIRED: dict[str, dict] = {
    "872130": {
        "family_section": 87,
        "replaced_by": [f"87213{i}" for i in range(1, 9)],
        "note": "Split in 2020 into 872131-872138; no single successor",
    },
}


@dataclass(frozen=True)
class ListItem:
    item_code: str
    description: str
    unit: str
    final_pay: bool
    spec_section: int


def read_item_list(path: Path) -> list[ListItem]:
    """Read the Caltrans bid item XLSX (header row: 'Item Code', 'Final Pay Item (F)', ...)."""
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.worksheets[0]
    items: list[ListItem] = []
    header_seen = False
    for row in ws.iter_rows(values_only=True):
        if not header_seen:
            header_seen = row[0] == "Item Code"
            continue
        code, final, desc, unit, section = (row + (None,) * 5)[:5]
        if code is None or desc is None:
            continue
        items.append(
            ListItem(
                item_code=str(code).strip().zfill(6),
                description=str(desc).strip(),
                unit=str(unit).strip().upper() if unit else "",
                final_pay=str(final or "").strip().upper() == "F",
                spec_section=int(str(section).strip()),
            )
        )
    wb.close()
    if not header_seen or not items:
        raise ValueError(f"{path} does not look like a Caltrans bid item list")
    return items


def build_item_master(con: duckdb.DuckDBPyConnection, item_list: Path) -> dict:
    """Fill item_master and create the bid_normalized view. Returns mapping statistics."""
    items = read_item_list(item_list)
    con.execute("DELETE FROM item_master")
    con.executemany(
        "INSERT INTO item_master VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, NULL)",
        [
            (
                i.item_code,
                i.description,
                i.unit,
                SECTION_FAMILY.get(i.spec_section),
                i.item_code[:2] in ("01", "02", "03", "04"),
                i.spec_section,
                i.final_pay,
            )
            for i in items
        ],
    )
    # Retired or unknown codes seen in the data (D-029).
    missing = con.execute("""
        SELECT item_code, any_value(item_description), mode(unit)
        FROM bid_item WHERE item_code NOT IN (SELECT item_code FROM item_master)
        GROUP BY item_code
    """).fetchall()
    for code, desc, unit in missing:
        info = RETIRED.get(code, {})
        section = info.get("family_section")
        con.execute(
            "INSERT INTO item_master VALUES (?, ?, ?, ?, ?, ?, FALSE, FALSE, ?)",
            [
                code,
                desc,
                unit,
                SECTION_FAMILY.get(section) if section else None,
                code[:2] in ("01", "02", "03", "04"),
                section,
                info.get("replaced_by"),
            ],
        )

    con.execute(
        "CREATE OR REPLACE TEMP TABLE unit_factor (unit VARCHAR, unit_norm VARCHAR, f DOUBLE)"
    )
    con.executemany(
        "INSERT INTO unit_factor VALUES (?, ?, ?)",
        [(u, n, f) for u, (n, f) in UNIT_FACTORS.items()],
    )
    # Persisted copy of the factors so the view works in later sessions.
    con.execute("CREATE OR REPLACE TABLE unit_conversion AS SELECT * FROM unit_factor")
    con.execute("""
        CREATE OR REPLACE VIEW bid_normalized AS
        SELECT b.bid_item_id, b.bid_rank, b.source_row_id,
               i.contract_id, i.item_code, m.description AS item_description,
               m.item_family, m.is_current,
               i.unit AS unit_original, i.quantity AS quantity_original,
               b.unit_price AS unit_price_original, b.total,
               coalesce(uc.unit_norm, i.unit) AS unit,
               i.quantity * coalesce(uc.f, 1) AS quantity,
               b.unit_price / coalesce(uc.f, 1) AS unit_price,
               (coalesce(uc.unit_norm, i.unit) <> m.unit AND m.is_current) AS unit_mismatch
        FROM bid b
        JOIN bid_item i USING (bid_item_id)
        LEFT JOIN item_master m USING (item_code)
        LEFT JOIN unit_conversion uc ON uc.unit = i.unit
    """)

    stats = con.execute("""
        SELECT count(*) AS bid_rows,
               count(*) FILTER (WHERE is_current) AS rows_current_code,
               count(*) FILTER (WHERE item_family IS NOT NULL) AS rows_with_family,
               count(*) FILTER (WHERE unit_mismatch) AS rows_unit_mismatch,
               count(*) FILTER (WHERE unit <> unit_original) AS rows_converted
        FROM bid_normalized
    """).fetchone()
    keys = (
        "bid_rows",
        "rows_current_code",
        "rows_with_family",
        "rows_unit_mismatch",
        "rows_converted",
    )
    out = dict(zip(keys, stats, strict=True))
    out["share_current_code"] = round(out["rows_current_code"] / out["bid_rows"], 4)
    out["item_list_codes"] = len(items)
    out["retired_codes_in_data"] = [m[0] for m in missing]
    return out
