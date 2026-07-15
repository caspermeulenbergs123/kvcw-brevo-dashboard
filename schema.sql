-- Brevo -> SQLite sync schema
-- Alles idempotent: opnieuw draaien werkt bij via INSERT OR REPLACE.

PRAGMA journal_mode = WAL;

-- Metadata per sync-run (wanneer, wat, hoeveel)
CREATE TABLE IF NOT EXISTS sync_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at      TEXT NOT NULL,
    scope       TEXT,          -- bv. "contacts,lists,segments,campaigns"
    contacts    INTEGER DEFAULT 0,
    lists       INTEGER DEFAULT 0,
    segments    INTEGER DEFAULT 0,
    campaigns   INTEGER DEFAULT 0,
    note        TEXT
);

-- Contacten
CREATE TABLE IF NOT EXISTS contacts (
    id                  INTEGER PRIMARY KEY,
    email               TEXT,
    firstname           TEXT,
    lastname            TEXT,
    email_blacklisted   INTEGER DEFAULT 0,
    sms_blacklisted     INTEGER DEFAULT 0,
    whatsapp_blacklisted INTEGER DEFAULT 0,
    created_at          TEXT,
    modified_at         TEXT,
    list_ids            TEXT,   -- JSON array, bv. [52,128,19]
    attributes          TEXT,   -- volledige attributes als JSON
    synced_at           TEXT
);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_modified ON contacts(modified_at);

-- Lijsten
CREATE TABLE IF NOT EXISTS lists (
    id                  INTEGER PRIMARY KEY,
    name                TEXT,
    folder_id           INTEGER,
    unique_subscribers  INTEGER DEFAULT 0,
    synced_at           TEXT
);

-- Segmenten
CREATE TABLE IF NOT EXISTS segments (
    id            INTEGER PRIMARY KEY,
    name          TEXT,
    category_name TEXT,
    updated_at    TEXT,
    synced_at     TEXT
);

-- Campagnes (metadata)
CREATE TABLE IF NOT EXISTS campaigns (
    id            INTEGER PRIMARY KEY,
    name          TEXT,
    subject       TEXT,
    type          TEXT,
    status        TEXT,
    sender_email  TEXT,
    sender_name   TEXT,
    tag           TEXT,
    scheduled_at  TEXT,
    sent_date     TEXT,
    recipients    TEXT,   -- JSON (lists/segments/exclusions)
    synced_at     TEXT
);

-- Campagne-statistieken (globalStats, 1 rij per campagne)
CREATE TABLE IF NOT EXISTS campaign_stats (
    campaign_id     INTEGER PRIMARY KEY,
    sent            INTEGER,
    delivered       INTEGER,
    soft_bounces    INTEGER,
    hard_bounces    INTEGER,
    unique_views    INTEGER,
    viewed          INTEGER,
    unique_clicks   INTEGER,
    clickers        INTEGER,
    unsubscriptions INTEGER,
    complaints      INTEGER,
    opens_rate      REAL,
    synced_at       TEXT,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);
