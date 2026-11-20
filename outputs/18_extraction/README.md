# 18 Extraction with citations

What BidLens reads out of the bid documents for contract 04-0W0504, with the page each
finding comes from (steps 3.3 and 3.4).

## How it works (decision D-052)

For each topic an estimator cares about (scope, time and damages, lane closures,
environmental limits, hazardous materials, site conditions, utilities, bid requirements,
submittals and payment terms), BidLens finds the most relevant passages in the special
provisions, addenda and information handout, and asks a language model to list the facts
on that topic. The model must copy a short exact quote for each one. BidLens then checks
that the quote really is in the passage and takes the document, page and section from
the passage itself, so a citation can never be made up. Bid items and quantities are not
read by the model at all: they come from the bid item list (stage 17).

## Local (Ollama, on this machine): llama3.1:8b

Run time 44.7 minutes for 10 topics.
215 items, of which 118 are bid items
with quantities read straight from the bid item list. Every item cites a document and page:
**yes**. The model's answers that quoted text not found in the cited
passage were dropped: 72.

| Category | Items kept | Returned by the model | Seconds |
| --- | ---: | ---: | ---: |
| scope | 4 | 25 | 436.6 |
| time_damages | 6 | 6 | 138.7 |
| traffic | 9 | 25 | 265.7 |
| environmental | 9 | 25 | 304.5 |
| hazardous | 0 | 25 | 307.3 |
| geotechnical | 15 | 25 | 277.3 |
| utilities | 22 | 25 | 225.8 |
| bid_requirements | 20 | 25 | 239.7 |
| submittals | 7 | 25 | 248.8 |
| payment | 5 | 25 | 236.5 |

Examples (two per topic):

| Topic | Finding | Value | Source |
| --- | --- | --- | --- |
| Scope of work | The contract covers construction on state highway in Alameda and Contra Costa counties at various locations. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 1 (Cover And Contents) |
| Scope of work | The contract covers various locations in Alameda and Contra Costa counties, including Route 4, 13, 24, 80, 84, etc. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 1 (Cover And Contents) |
| Working days and liquidated damages | The contract time is 600 working days. | 600 | Notice to Bidders and Special Provisions (includes the bid item list), page 13 (Notice To Bidders) |
| Working days and liquidated damages | Liquidated damages are limited to 5 percent of the total bid per occurrence. | 5% | Notice to Bidders and Special Provisions (includes the bid item list), page 58 (12 Temporary Traffic Control) |
| Traffic control and lane closures | Lane closures are allowed 24 hours a day, 7 days a week. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 102 (12 Temporary Traffic Control) |
| Traffic control and lane closures | Lane closures are not required for short duration closures of 1 hour or less or when the length of lane closure is 1/2 mile or less. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 102 (12 Temporary Traffic Control) |
| Environmental windows and permits | Do not bring pets onto the job site. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 105 (14 Environmental Stewardship) |
| Environmental windows and permits | Firearms are not allowed on the job site except for those carried by authorized security personnel or Local, State, or Federal law enforcement officials. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 105 (14 Environmental Stewardship) |
| Geotechnical and site conditions | If the specific site soil conditions differ from those specified in the AASHTO standard soil specification, the installation should be reviewed and approved by the Project Engineer. |  | Information Handout (materials and site reports), page 429 (Information Handout (materials and site reports)) |
| Geotechnical and site conditions | If rock or stiff soil is encountered, the posts and soil anchor may be installed by auguring and backfilling the hole. |  | Information Handout (materials and site reports), page 429 (Information Handout (materials and site reports)) |
| Utilities and third parties | Coordinate lane closures and traffic handling with the Engineer and with contractors of coincident or adjacent projects. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 28 (5 Control Of Work) |
| Utilities and third parties | Potential conflicts may not be limited to the contracts listed above. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 28 (5 Control Of Work) |
| Bid requirements | A mandatory virtual prebid meeting is required for all bidders. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 22 (2 Bidding) |
| Bid requirements | The virtual meeting will be a video conference meeting using Cisco Webex. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 22 (2 Bidding) |
| Submittals | Submit a resume of the safety representative before starting work on the project. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 24 (5 Control Of Work) |
| Submittals | Submit a copy of the safety representative's certificate for the Cal/OSHA 30-hour – Cal/OSHA Standards for the Construction Industry or OSHA 510 - OSHA Standards for the Construction Industry training course. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 24 (5 Control Of Work) |
| Payment and price terms | The Department does not adjust the unit price for an increase or decrease in the quantity of DRA on site meeting, DRB on site meeting, or hourly off-site DRA- or DRB-related task. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 30 (5 Control Of Work) |
| Payment and price terms | For progress payments, the total work completed for the TRO bid item is the number of working days shown for the pay period on the weekly statement of working days report. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 42 (9 Payment) |

## Local (Ollama, on this machine): qwen3:8b

Run time 58.6 minutes for 10 topics.
273 items, of which 118 are bid items
with quantities read straight from the bid item list. Every item cites a document and page:
**yes**. The model's answers that quoted text not found in the cited
passage were dropped: 68.

| Category | Items kept | Returned by the model | Seconds |
| --- | ---: | ---: | ---: |
| scope | 14 | 25 | 323.8 |
| time_damages | 17 | 25 | 312.7 |
| traffic | 0 | 18 | 535.3 |
| environmental | 23 | 23 | 346.3 |
| hazardous | 18 | 25 | 449.0 |
| geotechnical | 8 | 25 | 373.2 |
| utilities | 24 | 25 | 279.6 |
| bid_requirements | 25 | 25 | 258.6 |
| submittals | 11 | 25 | 316.8 |
| payment | 15 | 25 | 322.4 |

Examples (two per topic):

| Topic | Finding | Value | Source |
| --- | --- | --- | --- |
| Scope of work | The contract covers construction work on state highways in Alameda and Contra Costa counties at various locations. | Alameda and Contra Costa Counties | Notice to Bidders and Special Provisions (includes the bid item list), page 1 (Cover And Contents) |
| Scope of work | The contract includes work on multiple routes, including Route 4, 13, 24, 80, 84, and others. | Route 4, 13, 24, 80, 84, etc. | Notice to Bidders and Special Provisions (includes the bid item list), page 1 (Cover And Contents) |
| Working days and liquidated damages | The contractor must start job site activities within 55 days after receiving notice that the Contract has been approved by the Attorney General or the attorney appointed and authorized to represent the Department. | 55 | Notice to Bidders and Special Provisions (includes the bid item list), page 41 (8 Prosecution And Progress) |
| Working days and liquidated damages | The contractor must submit a notice 72 hours before starting job site activities. | 72 | Notice to Bidders and Special Provisions (includes the bid item list), page 42 (8 Prosecution And Progress) |
| Environmental windows and permits | The contractor must stop all work within a 50-foot radius of the discovery of nesting owls and raptors. | 50 | Notice to Bidders and Special Provisions (includes the bid item list), page 104 (14 Environmental Stewardship) |
| Environmental windows and permits | The contractor must stop all work within a 300-foot radius of the discovery of nesting owls and raptors. | 300 | Notice to Bidders and Special Provisions (includes the bid item list), page 104 (14 Environmental Stewardship) |
| Hazardous materials | Regulated material containing aerially deposited lead (ADL) must be managed under the rules and regulations of multiple agencies including the US EPA, Cal/OSHA, and the California Department of Recycling and Recovery. | multiple agencies including the US EPA, Cal/OSHA, and the California Department of Recycling and Recovery | Notice to Bidders and Special Provisions (includes the bid item list), page 105 (14 Environmental Stewardship) |
| Hazardous materials | Regulated material containing ADL is defined as material with average ADL concentrations over 80 mg/kg total lead or equal to or greater than 5 mg/L soluble lead tested using the California Waste Extraction Test or the Toxicity Characteristic Leaching Procedure. | 80 mg/kg total lead or equal to or greater than 5 mg/L soluble lead | Notice to Bidders and Special Provisions (includes the bid item list), page 106 (14 Environmental Stewardship) |
| Geotechnical and site conditions | The MAX-Tension® TL-2 system must be installed in soil that meets or exceeds the AASHTO standard soil specification. | AASHTO standard soil specification | Information Handout (materials and site reports), page 429 (Information Handout (materials and site reports)) |
| Geotechnical and site conditions | If the site soil conditions differ from the AASHTO standard soil specification, the installation must be reviewed and approved by the Project Engineer. | Project Engineer | Information Handout (materials and site reports), page 429 (Information Handout (materials and site reports)) |
| Utilities and third parties | Contractors must not trespass on railroad property within the project limits. | railroad property | Notice to Bidders and Special Provisions (includes the bid item list), page 28 (5 Control Of Work) |
| Utilities and third parties | Contractors must coordinate lane closures and traffic handling with the Engineer and adjacent contractors. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 28 (5 Control Of Work) |
| Bid requirements | The contractor must attend a mandatory virtual prebid meeting. | 04-Ala,CC-4,13, 24, 80, 84, etc.-Var | Notice to Bidders and Special Provisions (includes the bid item list), page 22 (2 Bidding) |
| Bid requirements | The virtual prebid meeting will be conducted using Cisco Webex. | Cisco Webex | Notice to Bidders and Special Provisions (includes the bid item list), page 22 (2 Bidding) |
| Submittals | The safety representative must submit a resume including education, safety training, and experience in heavy construction, heavy industrial, or oil and energy industry before starting work. | before starting work | Notice to Bidders and Special Provisions (includes the bid item list), page 24 (5 Control Of Work) |
| Submittals | The safety representative must submit a copy of the Cal/OSHA 30-hour or OSHA 510 training certificate as an informational submittal. |  | Notice to Bidders and Special Provisions (includes the bid item list), page 24 (5 Control Of Work) |
| Payment and price terms | The Department does not adjust the unit price for an increase or decrease in the quantity of DRA on site meetings. | 1 | Notice to Bidders and Special Provisions (includes the bid item list), page 30 (5 Control Of Work) |
| Payment and price terms | The Department does not adjust the unit price for an increase or decrease in the quantity of DRB on site meetings. | 2 | Notice to Bidders and Special Provisions (includes the bid item list), page 30 (5 Control Of Work) |

## Files

- `extracted_<mode>.csv`: every finding with its quote, document, page and section.
- `rejected_<mode>.csv`: model answers dropped because their quote was not in the passage.

## How it was produced

`uv run python -m bidlens.documents.extract 04-0W0504 --model <ollama model>`, once per
local model, one model loaded at a time (D-053, D-054). Everything runs on this machine at
no cost; the documents never leave it. The optional `--mode hosted` (Claude API, needs the
user's own key) is not used here. File names use the run's name, e.g. `local_qwen3-8b`.
Code in `src/bidlens/documents/extract.py`. Generated 2026-11-20.
