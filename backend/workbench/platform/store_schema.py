"""SQLite 建表语句（与 ``store.py`` 分开：DDL 是数据契约，会随时间只增不改）。

加表/加列时：在此追加 DDL，并把 ``SCHEMA_VERSION`` +1。
**不要改已有语句**——已发布的库靠前向迁移兼容，改历史语句会让老库和新库不一致。
"""

from __future__ import annotations

__all__ = ["SCHEMA_V1"]

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 页面保存的凭证（本库 > env > ~/.wmshare/credentials.env）
CREATE TABLE IF NOT EXISTS credentials (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    client_id     TEXT NOT NULL,
    client_secret TEXT NOT NULL,
    market        TEXT NOT NULL DEFAULT 'cn',
    updated_at    TEXT NOT NULL
);

-- 持仓档案：多套组合，positions 为 JSON
CREATE TABLE IF NOT EXISTS position_sets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL,
    positions  TEXT NOT NULL
);

-- 每次运行的快照（payload 为完整结果 JSON，可重放渲染）
CREATE TABLE IF NOT EXISTS snapshots (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    taken_at           TEXT NOT NULL,
    mode               TEXT NOT NULL DEFAULT 'real',
    tool               TEXT NOT NULL DEFAULT '',
    n_rows             INTEGER NOT NULL DEFAULT 0,
    as_of              TEXT NOT NULL DEFAULT '',
    payload            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_taken ON snapshots(taken_at);

-- 自选同步日志
CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at   TEXT NOT NULL,
    group_name  TEXT NOT NULL,
    action      TEXT NOT NULL,
    n_symbols   INTEGER NOT NULL DEFAULT 0,
    detail      TEXT,
    ok          INTEGER NOT NULL DEFAULT 1
);

-- 保存的选股表达式
CREATE TABLE IF NOT EXISTS saved_screens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    where_expr  TEXT NOT NULL,
    order_by    TEXT NOT NULL DEFAULT '',
    fields      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    last_run_at TEXT
);

-- 自选清单
CREATE TABLE IF NOT EXISTS watchlist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL,
    market     TEXT NOT NULL DEFAULT 'cn',
    group_name TEXT NOT NULL DEFAULT 'default',
    sort       INTEGER NOT NULL DEFAULT 0,
    note       TEXT NOT NULL DEFAULT '',
    added_at   TEXT NOT NULL,
    UNIQUE (code, market, group_name)
);

-- 判断留痕：当时怎么想 / 后来对了吗
CREATE TABLE IF NOT EXISTS judgement_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    topic        TEXT NOT NULL,
    as_of        TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_judgement_topic ON judgement_log(topic, created_at);

-- 主题缓存落盘（重启后仍有 last-known-good）
CREATE TABLE IF NOT EXISTS hub_state (
    topic      TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    as_of      TEXT NOT NULL DEFAULT '',
    fetched_at REAL NOT NULL,
    error      TEXT NOT NULL DEFAULT '',
    ttl_s      INTEGER NOT NULL DEFAULT 0,
    pinned     INTEGER NOT NULL DEFAULT 0
);

-- EC 消耗台账：归因到具体请求
CREATE TABLE IF NOT EXISTS ec_ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    target      TEXT NOT NULL,
    params_hash TEXT NOT NULL DEFAULT '',
    pred_lo     INTEGER,
    pred_hi     INTEGER,
    actual      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ec_ledger_at ON ec_ledger(at);

-- AI 助手会话（多轮消息整体存 JSON；本地单用户，无并发写同一会话）
CREATE TABLE IF NOT EXISTS assistant_sessions (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    messages   TEXT NOT NULL DEFAULT '[]'
);
"""
