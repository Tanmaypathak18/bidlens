# 01 Source review

Where the data comes from: the Caltrans sites, their rules, and sample pages.

- `source_review.md` is the review itself. It covers the Caltrans Contract Cost Data site, the HQ bid summary site and the item list, with their conditions of use and what each one contains.
- One saved page per endpoint used (6 files, no bidder names) is kept only as test fixtures in `tests/fixtures/caltrans/`, so the parsers are tested on the site's real layout.

How it was produced: by hand in step 1.1, with plain web requests at least 2 seconds apart. The HQ bid summary site's robots.txt disallows automated access, so no script ever requests it.
