-- Records Manager schema (SQLite)
-- Note: foreign keys are enforced only when each connection runs
--   PRAGMA foreign_keys = ON;
-- db.py does this on every connect.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL,
    email         TEXT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'user'
                          CHECK (role IN ('admin', 'user')),
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS patients (
    -- TEXT, not INTEGER: preserves leading zeros in hospital numbers
    hospital_num  TEXT    PRIMARY KEY,
    surname       TEXT    NOT NULL,
    first_names   TEXT    NOT NULL,
    box_no        TEXT    NOT NULL,
    scan_path     TEXT,               -- scanned form, if any (was the "PDF" column)
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Replaces borrower_table, borrowed_files and returned_files.
-- A loan is active while returned_on IS NULL.
CREATE TABLE IF NOT EXISTS loans (
    id            INTEGER PRIMARY KEY,
    hospital_num  TEXT    NOT NULL
                          REFERENCES patients (hospital_num)
                          ON UPDATE CASCADE
                          ON DELETE RESTRICT,
    borrower      TEXT    NOT NULL,
    department    TEXT    NOT NULL,
    reason        TEXT,
    borrowed_on   TEXT    NOT NULL DEFAULT (date('now')),
    returned_on   TEXT,
    recorded_by   INTEGER REFERENCES users (id),   -- was "Actioner"
    CHECK (returned_on IS NULL OR returned_on >= borrowed_on)
);

-- A file can only be out on one active loan at a time.
CREATE UNIQUE INDEX IF NOT EXISTS ux_loans_one_active
    ON loans (hospital_num)
    WHERE returned_on IS NULL;

-- Report queries: by date range and by borrower.
CREATE INDEX IF NOT EXISTS ix_loans_borrowed_on ON loans (borrowed_on);
CREATE INDEX IF NOT EXISTS ix_loans_borrower    ON loans (borrower);
