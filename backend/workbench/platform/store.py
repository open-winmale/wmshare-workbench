"""SQLite 存储：九张表，一把锁，文件权限 0600。

**为什么手写 SQL 而不引 ORM**：``dependencies = []`` 是产品价值的一部分
（用户 clone 下来就能跑）。九张表的读写全在这里，够用且可控。

**线程模型**：服务是 ``ThreadingHTTPServer``，每个请求一个线程。因此
``check_same_thread=False`` + 一把 ``threading.Lock`` 包住所有写操作。
SQLite 自身支持并发读，但 ``database is locked`` 在写并发下很常见，
单锁是最省心且对这个规模足够的方案。

**表清单**（4 张照搬 ``wmshare-tools`` + 5 张本项目新增）：

| 表 | 用途 |
|---|---|
| ``credentials`` | 页面保存的凭证（本库优先于 env / 文件） |
| ``position_sets`` | 持仓档案（多套组合） |
| ``snapshots`` | 每次运行的快照（JSON 可重放） |
| ``sync_log`` | 自选同步日志 |
| ``saved_screens`` | 保存的选股表达式（新增） |
| ``watchlist`` | 自选清单（新增） |
| ``judgement_log`` | 判断留痕：当时怎么想、后来对了吗（新增） |
| ``hub_state`` | 主题缓存落盘，重启后仍有 last-known-good（新增） |
| ``ec_ledger`` | EC 消耗台账，归因到具体请求（新增） |
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from .store_schema import SCHEMA_V1

__all__ = ["DEFAULT_DB_PATH", "Store", "SCHEMA_VERSION", "TABLES"]

#: 默认库路径：``~/.wmshare/workbench.db``（与 SDK 的凭证目录同源，便于一起备份）。
#: 测试必须用 ``Store(path=tmp_path/...)`` 覆盖。
DEFAULT_DB_PATH = Path.home() / ".wmshare" / "workbench.db"

#: 前向单向迁移版本。加表/加列时 +1 并在 ``_MIGRATIONS`` 追加。
SCHEMA_VERSION = 1

#: 九张表的名字（供 ``/api/health`` 与测试断言用）。
TABLES: tuple[str, ...] = (
    "credentials",
    "position_sets",
    "snapshots",
    "sync_log",
    "saved_screens",
    "watchlist",
    "judgement_log",
    "hub_state",
    "ec_ledger",
    "assistant_sessions",
)



def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Store:
    """SQLite 薄封装。

    所有公开方法都是线程安全的；写操作走同一把锁。
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._harden_permissions()

    # ---------------------------------------------------------------- 初始化

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA_V1)
            self._conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
                ("version", str(SCHEMA_VERSION)))
            self._conn.commit()

    def _harden_permissions(self) -> None:
        """库文件权限收到 0600——里面有明文凭证。

        与 wmshare SDK 的 ``~/.wmshare/credentials.env`` 同级敏感度。
        失败不抛（某些文件系统不支持 chmod），但会如实记录在 ``permission_ok``。
        """
        self.permission_ok = True
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            self.permission_ok = False

    # ---------------------------------------------------------------- 元信息

    def tables(self) -> list[str]:
        """实际存在的表名（供 ``/api/health`` 断言九表齐全）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return sorted(r["name"] for r in rows if not r["name"].startswith("sqlite_"))

    def version(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM schema_meta WHERE key='version'").fetchone()
        return int(row["value"]) if row else 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------- 凭证

    def get_credentials(self) -> dict[str, str] | None:
        """读取本库凭证；无记录返回 ``None``（区别于「有记录但为空」）。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT client_id, client_secret, market FROM credentials "
                "WHERE id=1").fetchone()
        if row is None:
            return None
        return {"client_id": row["client_id"],
                "client_secret": row["client_secret"],
                "market": row["market"]}

    def set_credentials(self, client_id: str, client_secret: str,
                        market: str = "cn") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO credentials"
                "(id, client_id, client_secret, market, updated_at) "
                "VALUES (1, ?, ?, ?, ?)",
                (client_id, client_secret, market, _now_iso()))
            self._conn.commit()

    def clear_credentials(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM credentials WHERE id=1")
            self._conn.commit()

    # ---------------------------------------------------------------- 快照

    def add_snapshot(self, *, tool: str, payload: Any, mode: str = "real",
                     as_of: str = "", n_rows: int = 0) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO snapshots(taken_at, mode, tool, n_rows, as_of, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_now_iso(), mode, tool, n_rows, as_of,
                 json.dumps(payload, ensure_ascii=False, default=str)))
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def latest_snapshot(self, tool: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM snapshots"
        args: tuple[Any, ...] = ()
        if tool:
            sql += " WHERE tool = ?"
            args = (tool,)
        sql += " ORDER BY id DESC LIMIT 1"
        with self._lock:
            row = self._conn.execute(sql, args).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["payload"] = json.loads(out["payload"])
        return out

    # ---------------------------------------------------------------- 持仓档案

    def save_position_set(self, name: str, positions: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO position_sets(name, updated_at, positions) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET updated_at=excluded.updated_at, "
                "positions=excluded.positions",
                (name, _now_iso(), json.dumps(positions, ensure_ascii=False)))
            self._conn.commit()

    def get_position_set(self, name: str) -> list[dict[str, Any]] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT positions FROM position_sets WHERE name=?", (name,)).fetchone()
        return json.loads(row["positions"]) if row else None

    def list_position_sets(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name FROM position_sets ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    # ---------------------------------------------------------------- 选股

    def save_screen(self, name: str, where: str, order: str = "",
                    fields: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO saved_screens(name, where_expr, order_by, fields, "
                "created_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET where_expr=excluded.where_expr, "
                "order_by=excluded.order_by, fields=excluded.fields",
                (name, where, order, fields, _now_iso()))
            self._conn.commit()

    def get_screen(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM saved_screens WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def list_screens(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM saved_screens ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- 自选

    def add_watch(self, code: str, market: str = "cn",
                  group: str = "default", note: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO watchlist(code, market, group_name, note, "
                "added_at) VALUES (?, ?, ?, ?, ?)",
                (code, market, group, note, _now_iso()))
            self._conn.commit()

    def remove_watch(self, code: str, market: str = "cn",
                     group: str = "default") -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM watchlist WHERE code=? AND market=? AND group_name=?",
                (code, market, group))
            self._conn.commit()

    def list_watch(self, group: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM watchlist"
        args: tuple[Any, ...] = ()
        if group:
            sql += " WHERE group_name=?"
            args = (group,)
        sql += " ORDER BY group_name, sort, code"
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- 判断留痕

    def add_judgement(self, topic: str, note: str, *,
                      as_of: str = "", payload_hash: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO judgement_log(topic, as_of, payload_hash, note, "
                "created_at) VALUES (?, ?, ?, ?, ?)",
                (topic, as_of, payload_hash, note, _now_iso()))
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def list_judgements(self, topic: str | None = None,
                        limit: int = 50) -> list[dict[str, Any]]:
        sql = "SELECT * FROM judgement_log"
        args: list[Any] = []
        if topic:
            sql += " WHERE topic=?"
            args.append(topic)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- hub 落盘

    def save_hub_state(self, topic: str, value: Any, *, as_of: str,
                       fetched_at: float, ttl_s: int = 0,
                       error: str = "", pinned: bool = False) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO hub_state"
                "(topic, value_json, as_of, fetched_at, error, ttl_s, pinned) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (topic, json.dumps(value, ensure_ascii=False, default=str), as_of,
                 fetched_at, error, ttl_s, 1 if pinned else 0))
            self._conn.commit()

    def load_hub_state(self) -> list[dict[str, Any]]:
        """重启后恢复 last-known-good。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM hub_state ORDER BY fetched_at DESC").fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            try:
                item["value"] = json.loads(item.pop("value_json"))
            except json.JSONDecodeError:
                item["value"] = None
            out.append(item)
        return out

    # ---------------------------------------------------------------- EC 台账

    def add_ec_ledger(self, target: str, *, pred_lo: int | None = None,
                      pred_hi: int | None = None, actual: int | None = None,
                      params_hash: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO ec_ledger(at, target, params_hash, pred_lo, pred_hi, "
                "actual) VALUES (?, ?, ?, ?, ?, ?)",
                (_now_iso(), target, params_hash, pred_lo, pred_hi, actual))
            self._conn.commit()

    def ec_today(self) -> dict[str, Any]:
        """今日累计消耗（按 ``actual`` 求和；无 ``actual`` 的不计入）。"""
        today = time.strftime("%Y-%m-%d")
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(actual), 0) AS total "
                "FROM ec_ledger WHERE at LIKE ?", (f"{today}%",)).fetchone()
        return {"calls": int(row["n"]), "ec_total": int(row["total"]),
                "day": today}


    # ------------------------------------------------------------ 助手会话

    def list_assistant_sessions(self) -> list[dict[str, Any]]:
        """会话列表（不含消息体；按最近更新排序）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, title, created_at, updated_at FROM assistant_sessions"
                " ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_assistant_session(self, session_id: str) -> dict[str, Any] | None:
        """取回一个会话（含 messages，已反序列化）。"""
        import json

        with self._lock:
            row = self._conn.execute(
                "SELECT id, title, created_at, updated_at, messages"
                " FROM assistant_sessions WHERE id = ?",
                (session_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        try:
            out["messages"] = json.loads(out.get("messages") or "[]")
        except (TypeError, ValueError):
            out["messages"] = []
        return out

    def save_assistant_session(self, session_id: str, title: str,
                               messages: list[dict[str, Any]]) -> None:
        """整体保存一个会话（消息量小，整体写比增量拼 SQL 可靠）。"""
        import json

        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO assistant_sessions(id, title, created_at,"
                " updated_at, messages) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET title=excluded.title,"
                " updated_at=excluded.updated_at, messages=excluded.messages",
                (session_id, title, now, now,
                 json.dumps(messages, ensure_ascii=False)))
            self._conn.commit()

    def delete_assistant_session(self, session_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM assistant_sessions WHERE id = ?", (session_id,))
            self._conn.commit()
        return cur.rowcount > 0


def open_store(path: Path | str | None = None) -> Store:
    """便捷构造（供 handler 用；测试须显式传 path）。"""
    return Store(path)


def _selftest() -> None:  # pragma: no cover - 手工冒烟用
    import tempfile

    with tempfile.TemporaryDirectory() as td, closing(open_store(Path(td) / "t.db")):
        pass
