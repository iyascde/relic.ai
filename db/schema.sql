-- Relic.ai SQLite schema
-- risk_scores: one row per PR analysis
-- incidents:   one row per incident issue, updated when closed

CREATE TABLE IF NOT EXISTS risk_scores (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_number         INTEGER NOT NULL,
    repo              TEXT    NOT NULL,
    score             INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    reasoning         TEXT    NOT NULL,
    high_risk_files   TEXT    NOT NULL DEFAULT '[]',   -- JSON array
    suggested_actions TEXT    NOT NULL DEFAULT '[]',   -- JSON array
    similar_incidents TEXT    NOT NULL DEFAULT '[]',   -- JSON array
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_risk_scores_pr_number ON risk_scores (pr_number);
CREATE INDEX IF NOT EXISTS idx_risk_scores_created_at ON risk_scores (created_at);

CREATE TABLE IF NOT EXISTS incidents (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_number   INTEGER NOT NULL,
    repo           TEXT    NOT NULL,
    title          TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    triage_brief   TEXT    NOT NULL DEFAULT '{}',      -- JSON object
    lessons        TEXT    NOT NULL DEFAULT '{}',      -- JSON object
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    resolved_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_issue_number ON incidents (issue_number);
CREATE INDEX IF NOT EXISTS idx_incidents_status        ON incidents (status);
