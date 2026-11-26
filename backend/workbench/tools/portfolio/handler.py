"""``/api/portfolio/run``：持仓账本。

四个 action 各自独立：

- ``valuate``：给定成交与当前价，算五法持仓与盈亏拆分
- ``save``：保存一套持仓（写本地库）
- ``list``：列出已保存的持仓档案
- ``load``：按名取回一套持仓——**没有它 ``save`` 就是黑洞**（存进去
  的成交拿不回来，只能存不能续）

**定价走一次批量请求**（``kline.snapshot`` 传列表），不逐票取——账本
可能几十只，逐票会打几十次。缺价的标的**不计入合计**并显式标注。

**已实现盈亏必须计入组合合计**，即使该标的已清仓（没有持仓行）——
账本内核的 ``mark_to_market`` 已经处理，handler 只需如实透传。

输入解析在 ``inputs``（三类输入来源 + 逐笔校验），本文件只做编排。
"""

from __future__ import annotations

from typing import Any

from ...client.ledger import BASIS_METHODS, InsufficientShares, twr, var
from ...client.ledger.positions import evaluate
from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import ToolError, err_from, fetch, str_param
from .inputs import parse_flows, parse_nav, parse_returns, parse_trades

__all__ = ["handle", "ACTIONS", "TARGET"]

TARGET = "kline.snapshot"

ACTIONS: tuple[str, ...] = ("valuate", "save", "list", "load")


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    action = str_param(params, "action") or "valuate"
    if action == "list":
        return _list(ctx)
    if action == "load":
        return _load(ctx, params)
    if action == "save":
        return _save(ctx, params)
    if action != "valuate":
        return err_from(ctx, ToolError(
            f"未知 action {action!r}；可选 {'/'.join(ACTIONS)}", code="param"))
    return _valuate(ctx, params)


# --------------------------------------------------------------------------
# 估值
# --------------------------------------------------------------------------

def _valuate(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    try:
        trades = parse_trades(params.get("trades"))
        method = str_param(params, "method") or "FIFO"
        if method not in BASIS_METHODS:
            raise ToolError(f"批次法只支持 {'/'.join(BASIS_METHODS)}，"
                            f"收到 {method!r}", code="param")
        codes = sorted({t.code for t in trades})
        prices, fx, as_of, price_dates, names = _price(ctx, codes)
        result = evaluate(trades, prices, fx, method)
        by_method = _all_methods(trades, prices, fx)
    except InsufficientShares as exc:
        return err_from(ctx, ToolError(str(exc), code="insufficient_shares"))
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    # 定价截止日是**数据事实**（每个快照自带 kline_date），取不到再回落
    span = sorted({d for d in price_dates.values() if d})
    as_of = span[-1] if span else as_of
    return ok_envelope(
        {
            "method": method,
            "methods": list(BASIS_METHODS),
            "rows": [_row(r, names.get(r.code, "")) for r in result.rows],
            "totals": {
                "value": result.value,
                "cost": result.cost,
                "realized": result.realized_total,
                "unrealized": result.unrealized_total,
                "valued": result.valued,
                "total": result.total,
                "complete": result.complete,
            },
            "by_method": by_method,
            # 有价标的各自的定价日（停牌票会停在更早的日期，如实给区间）
            "priced_as_of": span[-1] if span else "",
            "price_date_min": span[0] if span else "",
            "price_date_max": span[-1] if span else "",
            "twr": _twr_block(params),
            "var": _var_block(params),
        },
        as_of=as_of,
        meta={"note": "合计只覆盖有价标的（valued/total）；缺价不计入 0"},
        freshness="fresh",
        ec=EcEstimate(model="per_symbol_snapshot"),
        warnings=_warnings(result))


def _price(ctx: Any, codes: list[str]) -> tuple[dict[str, float | None],
                                                dict[str, float | None], str,
                                                dict[str, str],
                                                dict[str, str]]:
    """**一次**批量取价。取不到的标的给 ``None``（不填 0）。

    同时收集每个快照的 ``kline_date``（这条仓位的**定价截止日**，汇总成
    区间给前端）与 ``name``（23 字段快照自带，行表显示名称用）——两者
    都是已取回数据的免费透出，不发任何额外请求。

    **批量返回可能是 ``BatchResult`` 而非 dict**（2026-11-25 真实模式实测；
    ``sym`` 传列表时 SDK 包一层，快照表在 ``.results`` 属性里）。此前
    ``isinstance(raw, dict)`` 把它整个判空——**真实模式下持仓全部缺价**，
    而演示返回 dict 全绿，是「演示全绿、真实才崩」的又一例（D-25 同类）。
    """
    if not codes:
        return {}, {}, "", {}, {}
    try:
        raw, as_of = fetch(ctx, TARGET, {"sym": codes})
    except Exception:  # noqa: BLE001 - 定价失败让账面值缺失，但不终止整页
        empty: dict[str, str] = {}
        return ({c: None for c in codes}, {c: None for c in codes}, "",
                empty, empty)
    table = raw if isinstance(raw, dict) else getattr(raw, "results", None)
    if not isinstance(table, dict):
        table = {}
    prices: dict[str, float | None] = {}
    dates: dict[str, str] = {}
    names: dict[str, str] = {}
    for code in codes:
        prices[code], dates[code], names[code] = _price_row(table.get(code))
    # 演示与 A 股实时均为本币，汇率恒 1.0
    return prices, {c: 1.0 for c in codes}, as_of, dates, names


def _price_row(row: Any) -> tuple[float | None, str, str]:
    """单条快照 →（收盘价, 定价日, 名称）；缺失归 ``None``/空串（**不填 0**）。"""
    if not isinstance(row, dict):
        return None, "", ""
    close = row.get("close")
    price = float(close) if isinstance(close, (int, float)) else None
    name = row.get("name")
    return (price, str(row.get("kline_date") or "")[:10],
            str(name) if isinstance(name, str) else "")


def _all_methods(trades: list[Any], prices: dict[str, float | None],
                 fx: dict[str, float | None]) -> list[dict[str, Any]]:
    """五种批次法各算一遍（供对比）。

    ``SPECIFIC`` 在未指定 ``lot_id`` 时会抛错——捕获并标 ``error``，
    而不是让整个对比表崩掉。
    """
    out: list[dict[str, Any]] = []
    for method in BASIS_METHODS:
        try:
            val = evaluate(trades, prices, fx, method)
        except InsufficientShares as exc:
            out.append({"method": method, "error": str(exc)})
            continue
        out.append({
            "method": method,
            "realized": val.realized_total,
            "unrealized": val.unrealized_total,
            "value": val.value,
            "valued": val.valued,
            "total": val.total,
        })
    return out


def _row(row: Any, name: str = "") -> dict[str, Any]:
    return {
        "code": row.code, "name": name or "—", "shares": row.shares,
        "avg_price": row.avg_price, "price": row.price, "fx": row.fx,
        "cost": row.cost, "value": row.value,
        "unrealized": row.unrealized.total if row.unrealized else None,
        "realized": row.realized.total if row.realized else None,
    }


def _warnings(result: Any) -> list[str]:
    out: list[str] = []
    if result.total and result.valued < result.total:
        out.append(
            f"{result.total - result.valued} 只标的缺价，未计入市值合计"
            f"（有价 {result.valued}/{result.total}）")
    return out


def _twr_block(params: dict[str, Any]) -> dict[str, Any] | None:
    points = parse_nav(params.get("nav")) if params.get("nav") else None
    if not points:
        return None
    res = twr(points, parse_flows(params.get("flows")))
    return {"total": res.total, "annualized": res.annualized,
            "periods": res.periods, "skipped": res.skipped, "note": res.note}


def _var_block(params: dict[str, Any]) -> dict[str, Any] | None:
    returns = parse_returns(params.get("returns")) if params.get("returns") else None
    if returns is None:
        return None
    res = var(returns)
    return {"var": res.var, "confidence": res.confidence,
            "samples": res.samples, "used": res.used, "method": res.method}


# --------------------------------------------------------------------------
# 档案
# --------------------------------------------------------------------------

def _list(ctx: Any) -> dict[str, Any]:
    store = getattr(ctx, "store", None)
    names: list[str] = []
    if store is not None:
        try:
            names = store.list_position_sets()
        except Exception:  # noqa: BLE001 - 读库失败按「空档案」呈现
            names = []
    return ok_envelope(
        {"sets": names, "count": len(names)},
        as_of="",
        meta={"note": "持仓档案存在本地 SQLite"},
        freshness="fresh",
        ec=EcEstimate(model="local"))


def _load(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    """按名取回一套持仓（**零取数**：只读本地库）。

    **没有这个 action，``save`` 就是个黑洞**：存进去的成交只出现在
    ``list`` 的档案名里，用户拿不回具体内容，等于只能存不能续。
    """
    name = str_param(params, "name")
    if not name:
        return err_from(ctx, ToolError("缺少档案名（name）", code="missing_param"))
    store = getattr(ctx, "store", None)
    if store is None:
        return err_from(ctx, ToolError("存储未初始化", code="internal",
                                       action="report"))
    try:
        rows = store.get_position_set(name)
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)
    if rows is None:
        return err_from(ctx, ToolError(
            f"没有名为 {name!r} 的持仓档案", code="param", action="fix_input"))
    return ok_envelope(
        {"name": name, "trades": rows, "n_trades": len(rows)},
        as_of="",
        meta={"note": "从本地库读回；可直接改后重新估值或另存"},
        freshness="fresh",
        ec=EcEstimate(model="local"))


def _save(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = str_param(params, "name")
    if not name:
        return err_from(ctx, ToolError("缺少档案名（name）", code="missing_param"))
    store = getattr(ctx, "store", None)
    if store is None:
        return err_from(ctx, ToolError("存储未初始化", code="internal",
                                       action="report"))
    try:
        trades = parse_trades(params.get("trades"))
    except ToolError as exc:
        return err_from(ctx, exc)
    payload = [{"date": t.date, "code": t.code, "side": t.side,
                "shares": t.shares, "price": t.price, "fx": t.fx,
                "fee": t.fee, "lot_id": t.lot_id} for t in trades]
    try:
        store.save_position_set(name, payload)
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)
    return ok_envelope(
        {"saved": name, "n_trades": len(payload)},
        as_of="",
        meta={"note": "已写入本地库（按日期排序后保存）"},
        freshness="fresh",
        ec=EcEstimate(model="local"))
