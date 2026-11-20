# Cross-check summary

## Summary

| Check | Result |
| --- | --- |
| Low bidder's item prices compared (same contract, item and quantity) | 11,947 |
| Identical to the cent | 11,774 (98.6%) |
| Different, in contracts where the sources disagree on the low bidder | 173 prices in 11 contracts |
| Different on a single item only | 0 |
| Bidder count: cost database highest rank = ranked bidders in the summary | 657 of 665 contracts (4 fewer, 4 more) |

**What the differences mean:** in each flagged contract, the bidder ranked first in the cost database is not the low bidder in the bid summary, so almost every item price differs. This points to a ranking change (for example, a low bid that was later rejected), not to wrong numbers. Step 1.6 marks these contracts, and the models treat their rank-1 prices with care.
