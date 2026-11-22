# Item master and unit normalization (step 1.4)

**Source:** Caltrans 2026 Bid Items list, numerical XLSX, revised 10-19-26, with 2,633 codes. Retired codes seen in the data are kept and flagged. Families follow the 2026 Standard Specifications sections.

## Mapping

| | Bid rows | Share |
| --- | --- | --- |
| In-scope bid rows | 72,113 | 100% |
| Map to a current 2026 code | 71,747 | 99.49% |
| Retired code (listed below) | 366 | 0.51% |

The target was at least 95%.

**Units:** every in-scope row already uses its code's 2026 pay unit. No metric units appear, so no rows were converted and none were flagged. The conversion rules are in place for older data. Normalized values are in the `bid_normalized` view; the original values are never changed.

## Unmapped rows

| Item code | Description | Bid rows | Contracts | First bid | Last bid | Handling |
| --- | --- | --- | --- | --- | --- | --- |
| 872130 | MODIFYING EXISTING ELECTRICAL SYSTEM | 366 | 89 | 2018-01-10 | 2020-01-09 | Retired in 2020 and split into 872131 to 872138; kept as its own item |

## Item families (top 100 items)

| Family | Items | Contracts | Bid rows | Low-bid $ (millions) |
| --- | --- | --- | --- | --- |
| General and Overhead | 4 | 813 | 6,658 | 1,079.9 |
| Asphalt Surfacing | 9 | 609 | 9,372 | 1,050.6 |
| Traffic Control | 10 | 839 | 14,859 | 458.7 |
| Electrical and Signals | 12 | 364 | 2,486 | 371.8 |
| Structural Concrete and Reinforcement | 8 | 350 | 3,767 | 347.9 |
| Concrete Pavement | 5 | 93 | 553 | 269.5 |
| Steel Structures, Signs and Painting | 5 | 58 | 399 | 260.8 |
| Earthwork and Clearing | 8 | 547 | 5,797 | 251.3 |
| Bridge Rehabilitation and Removal | 5 | 192 | 1,790 | 183.6 |
| Fencing, Guardrail and Barriers | 8 | 286 | 3,595 | 156.2 |
| Base and Subbase | 5 | 304 | 1,863 | 143.1 |
| Striping and Markings | 4 | 643 | 6,341 | 88.9 |
| Water Pollution and Site Management | 4 | 832 | 8,744 | 85.2 |
| Drainage | 2 | 159 | 903 | 35.3 |
| Piling | 3 | 66 | 422 | 33.5 |
| Minor Concrete and Miscellaneous | 3 | 198 | 1,116 | 32.3 |
| Walls and Ground Support | 3 | 21 | 133 | 26.3 |
| Landscape and Erosion Control | 2 | 377 | 3,315 | 23.5 |

18 of the 19 families appear in the top 100 (Environmental and Existing Facilities has none). The thinnest are Walls and Ground Support (21 contracts) and Piling (66 contracts). Their test sets in step 2.1 may be small; a family that is too small there is merged with a neighbour.
