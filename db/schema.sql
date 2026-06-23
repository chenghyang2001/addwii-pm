-- addwii-pm 完整資料庫 Schema：任務追蹤、筆記、會議記錄、反思、Discord 訊息快取
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS agents (
    role             TEXT PRIMARY KEY,
    display_name     TEXT NOT NULL,
    discord_user_id  INTEGER NOT NULL UNIQUE,
    bot_discord_id   INTEGER,
    reports_to       TEXT REFERENCES agents(role),
    persona_file     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    detail      TEXT,
    assigner    TEXT NOT NULL REFERENCES agents(role),
    assignee    TEXT NOT NULL REFERENCES agents(role),
    status      TEXT NOT NULL DEFAULT 'assigned'
                CHECK (status IN ('assigned','in_progress','done','blocked','cancelled')),
    priority    TEXT NOT NULL DEFAULT 'normal',
    deadline    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee_status ON tasks(assignee, status);

CREATE TABLE IF NOT EXISTS task_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    actor       TEXT NOT NULL REFERENCES agents(role),
    event       TEXT NOT NULL,
    from_status TEXT,
    to_status   TEXT,
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner      TEXT NOT NULL REFERENCES agents(role),
    content    TEXT NOT NULL,
    tags       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meeting_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner        TEXT NOT NULL REFERENCES agents(role),
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    decisions    TEXT,
    action_items TEXT,
    meeting_at   TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reflections (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner      TEXT NOT NULL REFERENCES agents(role),
    content    TEXT NOT NULL,
    mood       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id   INTEGER NOT NULL,
    message_id   INTEGER,
    speaker_kind TEXT NOT NULL CHECK (speaker_kind IN ('human','agent')),
    role         TEXT REFERENCES agents(role),
    text         TEXT NOT NULL,
    hop          INTEGER DEFAULT 0,
    intent_json  TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(channel_id, message_id, speaker_kind)
);
