# 17 Document parsing

The bid package turned into text BidLens can search and cite (step 3.2).

## What we did

Each document of contract 04-0W0504 that BidLens reads was turned into text page by page.
The special provisions were split into their numbered sections (for example "8 Prosecution
And Progress"), keeping the most recent section number mentioned (for example 8-1.05).
The text was then cut into short passages ("chunks") that never cross a page or a
section, so every fact pulled from them in step 3.3 can cite one exact page.

| Document | Pages | Empty pages | Chunks |
| --- | ---: | ---: | ---: |
| Information Handout (materials and site reports) | 673 | 23 | 1,243 |
| Addendum No. 1 | 1 | 0 | 2 |
| Addendum No. 2 | 3 | 0 | 4 |
| Addendum No. 3 | 1 | 0 | 2 |
| Forms for bid | 3 | 2 | 1 |
| Notice to Bidders and Special Provisions (includes the bid item list) | 124 | 4 | 236 |

Empty pages are scanned images or figures without text; they are listed in
`empty_pages.csv` and not read in v1. The plans are drawings without text and are not read.

## The bid item list

The list on the special provisions' Bid Item List pages was read row by row, and then
every addendum's revised list was applied:

| Addendum | Item | Change | Was | Now |
| --- | --- | --- | --- | --- |
| 04-0W0504ad2.pdf p3 | 0026 | deleted | 170105 CLEARING AND GRUBBING (ACRE) |  |
| 04-0W0504ad2.pdf p3 | 0118 | deleted | 999990 MOBILIZATION |  |
| 04-0W0504ad2.pdf p3 | 0119 | added |  | 170103 CLEARING AND GRUBBING (LS) |
| 04-0W0504ad2.pdf p3 | 0120 | added |  | 999990 MOBILIZATION |

The result has 118 items. Checked against the bid summary's item list
for the same contract (118 items): **They match exactly**: same item numbers, codes, units and quantities.


## Files

- `documents.csv`: pages, empty pages, characters and chunks per document.
- `special_provision_sections.csv`: each section of the special provisions with its pages.
- `bid_item_list.csv`: the final bid item list with the page each row came from.
- `addendum_changes.csv`: the bid item changes made by addenda.
- `empty_pages.csv`: pages without text.

The page text and chunks themselves are in `data/interim/docs/04-0W0504/` (not committed).

## How it was produced

`uv run python -m bidlens.documents.parse 04-0W0504` (code in
`src/bidlens/documents/parse.py`). Generated 2026-11-20.
