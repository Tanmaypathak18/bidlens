# 16 Bid package

The sample bid package BidLens reads in Phase 3: Caltrans contract 04-0W0504 (step 3.1).

## Which project and why

Contract 04-0W0504: highway work in Alameda and Contra Costa counties (trash capture devices,
maintenance vehicle pullouts, guardrail, erosion control and lighting), engineer's estimate
$22.7 million, 120 bid items, bids opened 17 September 2026. Bids are already open, so the
draft estimate BidLens builds from these documents can be checked against the real bids.
It has three addenda and an information handout.

## The files

| File | What it is | Pages | Read by BidLens |
| --- | --- | ---: | --- |
| `04-0W0504.pdf` | Bid summary (bid results; holds bidder names, never an input or output) | 30 | no |
| `04-0W0504IH.pdf` | Information Handout (materials and site reports) | 673 | yes |
| `04-0W0504ad1.pdf` | Addendum No. 1 | 1 | yes |
| `04-0W0504ad2.pdf` | Addendum No. 2 | 3 | yes |
| `04-0W0504ad3.pdf` | Addendum No. 3 | 1 | yes |
| `04-0W0504ad3fw.pdf` | Project plans revised by Addendum 3 (drawings) | 93 | no |
| `04-0W0504formsforbid.pdf` | Forms for bid | 3 | yes |
| `04-0W0504fw.pdf` | Project plans (drawings) | 93 | no |
| `04-0W0504sp.pdf` | Notice to Bidders and Special Provisions (includes the bid item list) | 124 | yes |
| `04-0W0504supplemental_info.zip` | Supplemental information (cross sections) | 2 files | no |

The documents are not in this repository: Caltrans serves them from a site that does not
allow automated downloads, so they were downloaded by hand from the contract's page
(https://ppmoe.dot.ca.gov/cc?id=cc_advertisement_details&ad_id=04-0W0504) into `data/raw/bid_package/04-0W0504/`. `manifest.csv` lists each file's
size and SHA-256 fingerprint, so anyone can check they have the same files. The plans are
drawings without a text layer and are not read in v1. The bid summary is the bid result,
not part of the package; it names bidders and is never used here.

## How it was produced

`uv run python -m bidlens.documents.manifest 04-0W0504`. Generated 2026-11-20.
