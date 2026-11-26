"""``/api/watchlist/run``：自选批量行情。

**列走 ``kline.snapshot`` 批量（23 字段），live_many 伴取日期与盘中价。**

2026-11-25 换源：旧入口 live_many 真实只有 13 字段（无 name/chg_5d/
chg_20d/vol_ratio_5），名称与三个指标列在真实模式恒空（D-27）。
snapshot 批量一次全齐，但批量路由不物化 ``kline_date``——live_many
本来就是**盘中日K**（休市=最近收盘快照），伴取它同时补行级日期；
``live=True`` 时现价/涨跌幅/额/市值以它为准（标 ``live``）。

**降级路径**：免注册被拒批量 → 逐票**单票 snapshot**（23 字段自带
kline_date），不用只有 9 字段的 ``kline.query_last``。

**批量返回可能是 ``BatchResult``**（``.results``，持仓页 D-25 同款）。
请求次数与降级原因如实进信封；**空清单不自动填充**。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import ToolError, bad_params, err_from, fetch, str_list_param, str_param
from . import mutate

__all__ = ["handle", "ACTIONS", "DEFAULT_SYMBOLS", "TARGET", "BATCH_TARGET"]

#: 支持的 action（`quotes` 默认；`add`/`remove` 只写本地库、零取数）。
ACTIONS: tuple[str, ...] = ("quotes", "add", "remove")

#: 批量入口（``sym`` 传列表，SDK 自动路由批量；23 字段含名称与区间指标；
#: 免注册下可能被策略拒绝）。
BATCH_TARGET = "kline.snapshot"

#: 逐票降级入口（免注册可用；**同一个 snapshot**，单票同样 23 字段）。
TARGET = "kline.snapshot"

#: 日期伴取：批量快照路由不物化 ``kline_date``（索引未物化），行级截止日
#: 从 live_many 的 ``date`` 来（1 次请求；失败只丢页级日期，不丢列）。
DATE_TARGET = "kline.query_last_live_many"

#: 首次打开时的**示例**清单（不是自动写入的持仓）。
DEFAULT_SYMBOLS: tuple[str, ...] = ("600519", "000001", "300750", "688981", "601318")

#: 行情表要展示的列（顺序即 UI 列顺序）。
COLUMNS: tuple[tuple[str, str], ...] = (
    ("symbol", "代码"),
    ("name", "名称"),
    ("close", "最新价"),
    ("percent", "涨跌幅"),
    ("chg_5d", "5 日"),
    ("chg_20d", "20 日"),
    ("vol_ratio_5", "量比"),
    ("amount", "成交额"),
    ("mv", "总市值"),
)


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    action, bad = _route(params)
    if bad is not None:
        return bad
    if action in ("add", "remove"):
        return mutate.run(ctx, action, params)

    try:
        symbols = _resolve_symbols(ctx, params)
    except Exception as exc:  # noqa: BLE001 - 参数错误统一分级
        return err_from(ctx, exc)
    if not symbols:
        return _empty(ctx)

    live = bool(params.get("live"))
    try:
        rows, as_of, note, requests = _quotes(ctx, symbols, live)
    except Exception as exc:  # noqa: BLE001 - 非权限类失败整体失败（可读信封）
        return err_from(ctx, exc)
    return _quotes_envelope(ctx, symbols, rows, as_of, note, requests)


def _route(params: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """解析 action；未知时返回可读错误信封（handle 复杂度过 12 才拆出）。"""
    action = str_param(params, "action") or "quotes"
    if action in ACTIONS:
        return action, None
    return action, err_from_args(
        ToolError(f"未知 action {action!r}；可选 {'/'.join(ACTIONS)}",
                  code="param"))


def err_from_args(exc: BaseException) -> dict[str, Any]:
    """无 ``ctx`` 场景的错误信封（``bad_params`` 的别名，语义更直白）。"""
    return bad_params(str(exc), "param")


def _empty(ctx: Any) -> dict[str, Any]:
    """空清单信封：**零请求**，且不自动填充样例。"""
    return ok_envelope(
        {"symbols": [], "rows": [], "count": 0,
         "columns": [{"key": k, "label": v} for k, v in COLUMNS],
         "request_count": 0, "source": TARGET, "degraded": False,
         "groups": _groups(ctx)},
        as_of="",
        meta={"note": "自选清单为空"}, freshness="fresh",
        ec=EcEstimate(model="zero_cost"))


def _quotes_envelope(ctx: Any, symbols: list[str],
                     rows: list[dict[str, Any]], as_of: str,
                     note: str, requests: int) -> dict[str, Any]:
    """行情信封：把「发了几次请求」如实写进 ``meta`` 与 ``request_count``。"""
    degraded = bool(note)
    # 批量路径行级日期全空（快照不物化 + 伴取也失败）→ 页级「截至未知」要告警
    date_lost = (not degraded and bool(rows)
                 and not any(r.get("kline_date") for r in rows))
    warnings = [w for w in (note,
                            "行情日期不可用：批量快照不物化行级截止日，"
                            "页级截至未知" if date_lost else "") if w]
    return ok_envelope(
        {
            "symbols": symbols,
            "rows": rows,
            "columns": [{"key": k, "label": v} for k, v in COLUMNS],
            "count": len(rows),
            "request_count": requests,
            "source": TARGET if degraded else BATCH_TARGET,
            "degraded": degraded,
            "groups": _groups(ctx),
        },
        as_of=as_of,
        meta={"note": note or "批量快照 + 日期伴取：2 次请求覆盖全部标的"
                              "（含名称与 5日/20日/量比）",
              "requests": requests},
        freshness="fresh",
        ec=EcEstimate(model="per_symbol_rows"),
        warnings=warnings)


def _resolve_symbols(ctx: Any, params: dict[str, Any]) -> list[str]:
    """显式传入优先；否则读本地自选；都没有就用示例清单。"""
    explicit = str_list_param(params, "symbols")
    if explicit:
        return explicit
    group = str_param(params, "group")
    store = getattr(ctx, "store", None)
    if store is not None:
        try:
            rows = store.list_watch(group or None)
        except Exception:  # noqa: BLE001 - 读库失败不该让整页崩
            rows = []
        codes = [str(r.get("code")) for r in rows if r.get("code")]
        if codes:
            return codes
    return list(DEFAULT_SYMBOLS)


def _quotes(ctx: Any, symbols: list[str],
            live: bool) -> tuple[list[dict[str, Any]], str, str, int]:
    """取报价：先批量，被策略拒则逐票降级。

    返回 ``(rows, as_of, note, requests)``；``note`` 非空 = 降级（进
    ``warnings``），``requests`` 是真实请求次数（批量 2、降级 N）。
    """
    table, as_of = _try_batch(ctx, symbols)
    if table is None:
        rows, as_of, note = _fallback(ctx, symbols)
        return rows, as_of, note, len(symbols)
    live_rows: dict[str, dict[str, Any]] = {}
    try:  # 盘中伴取（live_many 本就是盘中日K）：失败只丢日期/实时价
        raw, _ = fetch(ctx, DATE_TARGET, {"syms": symbols})
        if isinstance(raw, dict):
            live_rows = {s: r for s, r in raw.items() if isinstance(r, dict)}
    except Exception:  # noqa: BLE001 - 伴取失败只降级
        pass
    rows = [_row_from(_merge_live(table.get(sym), live_rows.get(sym), live),
                      sym)
            for sym in symbols]
    # 信封 as_of = 各行日期 max（数据事实），扔掉它页顶就没有「截至」
    return rows, _max_kline_date(rows) or as_of, "", 2


def _merge_live(row: Any, live_row: Any, live: bool) -> Any:
    """快照行 ⊕ 盘中快照。日期总是回填；``live=True`` 时现价/涨跌幅/
    额/市值以 live 为准并标 ``live``。live 日期不早于快照才覆盖（停牌票
    的 live 停在更早，覆盖会把现价倒回停牌前）。「实时」= live 端点的
    最新快照：休市时值即最近收盘价，不冒充盘中跳动。
    """
    if not isinstance(row, dict):
        return row
    merged = dict(row)
    if not isinstance(live_row, dict):
        return merged
    date = str(live_row.get("date") or "")[:10]
    if not date or date < str(merged.get("kline_date") or ""):
        return merged
    merged["kline_date"] = date
    if live:
        for key in ("close", "percent", "amount", "mv"):
            value = live_row.get(key)
            if value is not None:
                merged[key] = value
        merged["live"] = True
    return merged


def _try_batch(ctx: Any,
               symbols: list[str]) -> tuple[dict[str, Any] | None, str]:
    """批量取数；无权时返回 ``(None, "")`` 表示该走降级。

    ``sym`` 传列表时 SDK 包一层 ``BatchResult``（快照表在 ``.results``），
    与持仓页定价同款（D-25）；演示返回普通 dict。
    """
    try:
        raw, as_of = fetch(ctx, BATCH_TARGET, {"sym": symbols})
    except Exception as exc:  # noqa: BLE001 - 仅对权限类失败降级
        if _is_policy_denied(exc):
            return None, ""
        raise
    table = raw if isinstance(raw, dict) else getattr(raw, "results", None)
    return (table if isinstance(table, dict) else {}), as_of


def _is_policy_denied(exc: BaseException) -> bool:
    """是否是「免注册权限不足」这类失败。**只对这一类降级**：网络超时/
    限流降级会把 1 个失败放大成 N 个，那是把问题变糟而不是变好。"""
    text = f"{type(exc).__name__}: {exc}"
    return ("POLICY_DENIED" in text or "免注册访问被拒绝" in text
            or type(exc).__name__ == "AuthError")


def _fallback(ctx: Any,
              symbols: list[str]) -> tuple[list[dict[str, Any]], str, str]:
    """逐票取数（免注册可用）。失败的单票保留一行并标缺失。"""
    rows: list[dict[str, Any]] = []
    as_of = ""
    failures = 0
    for sym in symbols:
        try:
            raw, got_as_of = fetch(ctx, TARGET, {"sym": sym})
        except Exception:  # noqa: BLE001 - 单票失败不该让整表消失
            failures += 1
            rows.append(_row_from(None, sym))
            continue
        rows.append(_row_from(raw, sym))
        as_of = as_of or got_as_of

    note = (f"批量接口在当前访问方式下不可用（免注册策略限制），"
            f"已逐票取数：本页发了 {len(symbols)} 次请求。"
            f"配置自有凭证可恢复单次批量。")
    if failures:
        note += f" 其中 {failures} 只取数失败，已标为缺失。"
    # 逐票路径同样用 max(行日期) 收口——此前只留第一只成功票的日期，
    # 其余票各自的 kline_date 被丢弃（页顶「截至」可能比数据实际早/晚）
    return rows, _max_kline_date(rows) or as_of, note


def _row_from(raw: Any, sym: str) -> dict[str, Any]:
    """把一条 23 字段快照映射成表格行；缺失时保留行并标 ``missing``。

    缺数据的标的**不从表里消失**；名称缺失回落 **"—"** 而不是代码——
    拿代码冒充名称会让用户以为是真名（换源前真实模式就是这么显示的）。
    ``kline_date`` 是这一行的数据截止日（停牌票停在停牌前）。
    """
    if not isinstance(raw, dict):
        return {"symbol": sym, "name": "—", "close": None, "percent": None,
                "chg_5d": None, "chg_20d": None, "vol_ratio_5": None,
                "amount": None, "mv": None, "kline_date": None,
                "missing": True}
    row = {key: raw.get(key) for key, _ in COLUMNS}
    row["symbol"] = row.get("symbol") or sym
    if row.get("name") in (None, ""):
        row["name"] = "—"
    if raw.get("live"):
        row["live"] = True
    row["kline_date"] = str(raw.get("kline_date") or raw.get("date") or "")[:10]
    return row


def _max_kline_date(rows: list[dict[str, Any]]) -> str:
    """各行 ``kline_date`` 的最大值（整页已知的数据截止日）。"""
    dates = [str(r.get("kline_date") or "") for r in rows]
    return max(dates) if dates else ""


def _groups(ctx: Any) -> list[str]:
    """已有的自选分组（供 UI 分组切换）。"""
    store = getattr(ctx, "store", None)
    if store is None:
        return []
    try:
        rows = store.list_watch()
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for r in rows:
        g = str(r.get("group_name") or "")
        if g and g not in out:
            out.append(g)
    return out
