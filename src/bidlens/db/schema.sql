-- BidLens data model (step 1.3). Readable natural keys; exact decimal prices in the original unit.
-- Documented in docs/data_dictionary.md.

-- One row per bid opening. Re-advertised contracts get one row per opening.
CREATE TABLE contract (
    contract_id         VARCHAR PRIMARY KEY,      -- '<contract number>_<bid open date>'
    contract_number     VARCHAR NOT NULL,         -- Caltrans EA, e.g. '04-1Q7004'
    bid_open_date       DATE    NOT NULL,
    district            VARCHAR NOT NULL,         -- '04', from the contract number
    county              VARCHAR,                  -- e.g. 'SON'
    location            VARCHAR,                  -- County-Route-Postmile as published
    type_of_work        VARCHAR,                  -- contract description
    in_contract_list    BOOLEAN NOT NULL,         -- found by the contract list
    n_bidders_sv08      INTEGER,                  -- highest bid rank seen in item bids
    -- Contract-level fields from bid summary PDFs (step 1.5); NULL when missing.
    has_bid_summary     BOOLEAN NOT NULL DEFAULT FALSE,
    project_id          VARCHAR,
    n_items             INTEGER,
    proposals_issued    INTEGER,
    working_days        INTEGER,
    n_bidders_reported  INTEGER,                  -- as printed, may include irregular bids
    n_bidders           INTEGER,                  -- ranked (regular) bidders
    engineers_estimate  DECIMAL(18, 2),
    low_bid_cost        DECIMAL(18, 2),
    low_bid_total       DECIMAL(18, 2),           -- = cost, or cost + time for A+B
    second_bid_total    DECIMAL(18, 2),
    is_a_plus_b         BOOLEAN,
    bid_summary_file    VARCHAR,
    bid_summary_ocr     BOOLEAN,                  -- read by OCR
    UNIQUE (contract_number, bid_open_date),
    CHECK (engineers_estimate IS NULL OR engineers_estimate > 0),
    CHECK (working_days IS NULL OR working_days > 0)
);

-- Caltrans item list (step 1.4). Retired codes seen in the data are
-- kept with is_current = FALSE.
CREATE TABLE item_master (
    item_code           VARCHAR PRIMARY KEY,      -- 6 digits
    description         VARCHAR NOT NULL,
    unit                VARCHAR,                  -- normalized pay unit
    item_family         VARCHAR,                  -- 19 groups by spec section
    is_one_time_use     BOOLEAN NOT NULL DEFAULT FALSE,
    spec_section        INTEGER,                  -- 2026 Standard Specifications section
    final_pay           BOOLEAN NOT NULL DEFAULT FALSE,
    is_current          BOOLEAN NOT NULL,         -- on the 2026 list
    replaced_by         VARCHAR[],                -- successors of a retired code
    CHECK (length(item_code) = 6)
);

-- One priced line of a contract opening.
CREATE TABLE bid_item (
    bid_item_id         VARCHAR PRIMARY KEY,      -- '<contract_id>_<item code>_<n>'
    contract_id         VARCHAR NOT NULL REFERENCES contract (contract_id),
    item_code           VARCHAR NOT NULL,         -- as published (mapped to item_master in 1.4)
    item_description    VARCHAR NOT NULL,
    unit                VARCHAR NOT NULL,         -- original Caltrans unit
    quantity            DECIMAL(18, 4) NOT NULL,  -- 1 for lump sum
    CHECK (quantity > 0)
);

-- One bidder's price on one bid item. No bidder identities are stored.
CREATE TABLE bid (
    bid_item_id         VARCHAR NOT NULL REFERENCES bid_item (bid_item_id),
    bid_rank            INTEGER NOT NULL,         -- bidder's overall rank on the contract
    unit_price          DECIMAL(18, 4) NOT NULL,
    total               DECIMAL(18, 2) NOT NULL,
    source_row_id       BIGINT  NOT NULL UNIQUE,  -- sv08data details.php?Num=
    PRIMARY KEY (bid_item_id, bid_rank),
    CHECK (bid_rank >= 1),
    CHECK (unit_price >= 0)
);

-- Caltrans Construction Cost Index (filled in step 2.2).
CREATE TABLE cost_index (
    series              VARCHAR NOT NULL,
    year                INTEGER NOT NULL,
    quarter             INTEGER NOT NULL,
    value               DOUBLE  NOT NULL,
    PRIMARY KEY (series, year, quarter),
    CHECK (quarter BETWEEN 1 AND 4)
);
