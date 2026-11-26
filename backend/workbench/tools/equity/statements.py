"""个股研究 —— 财务报表分区（``cli.statements.*`` 门面，跨期透视）。

**全部四张表走公开门面**（``statements.income/balance/cashflow/indicators``），
**不碰内部命名空间**。门面原生支持季报：``period='annual'|'quarter'``
（季报为累计档，Q3 = 前三季；``years`` 1..12）。

**返回形状**（samples 实证）：``list[{cn, k, vals: {期次: 值}}]``——
每个科目一行、各期一列；门面直返 DataFrame 时过 ``as_records`` 归一，
两种路径同构。期次键：年报档为年份（``2025``），季报档为 ``2026-Q3``。
"""

from __future__ import annotations

from typing import Any

from ...tools._shared import ToolError, as_records, fetch, str_param
from .indicators import build as build_indicators

__all__ = ["build", "STATEMENT_DOMAINS"]

#: 报表简称 → ``statements`` 门面的方法名。
STATEMENT_DOMAINS: dict[str, str] = {
    "income": "income",
    "balance": "balance",
    "cashflow": "cashflow",
}


def build(ctx: Any, symbol: str,
          params: dict[str, Any]) -> tuple[Any, str, list[str]]:
    """财务报表科目（跨期 ``vals``）。

    返回 ``rows`` + ``periods``（列名，最近一期在前），由前端按
    「科目 × 期次」渲染；``period`` 回显给前端（年报/季报档）。
    """
    kind = str_param(params, "domain") or "indicators"
    period = str(params.get("period") or "annual")
    if period not in ("annual", "quarter"):
        raise ToolError(f"period 只支持 annual/quarter，收到 {period!r}",
                        code="param")
    if kind == "indicators":
        return build_indicators(ctx, symbol, params)
    method = STATEMENT_DOMAINS.get(kind)
    if method is None:
        raise ToolError(
            f"domain 只支持 {'/'.join(STATEMENT_DOMAINS)}，收到 {kind!r}",
            code="param")
    raw, as_of = fetch(ctx, f"statements.{method}",
                       {"symbol": symbol, "years": 5, "period": period},
                       facade=("statements", method))
    rows = _as_statement_rows(raw)
    if not rows:
        raise ToolError(f"{symbol} 的 {kind} 报表未取到", code="upstream",
                        action="retry")
    return ({"domain": kind, "sdk_domain": f"statements.{method}",
             "period": period,
             "periods": _periods(rows), "rows": rows}, as_of, [])


def _as_statement_rows(raw: Any) -> list[dict[str, Any]]:
    """归一成 ``[{k, cn, vals}]``。

    形状归一交给 ``tools._shared.as_records``（唯一实现）；这里只做**业务过滤**：
    没有跨期 ``vals`` 的行不是报表科目（可能是错误行或占位行），丢掉。
    另接受 ``{data: [...]}`` / ``{rows: [...]}`` 这种包装。
    """
    data = raw
    if isinstance(raw, dict) and "vals" not in raw:
        data = raw.get("data", raw.get("rows"))
    out: list[dict[str, Any]] = []
    for row in as_records(data):
        vals = row.get("vals")
        if not isinstance(vals, dict):
            continue
        out.append({"k": row.get("k"), "cn": row.get("cn") or row.get("k"),
                    "vals": vals})
    return out


def _periods(rows: list[dict[str, Any]]) -> list[str]:
    """期次列名（**降序**：最近一期在前，符合财务表的阅读习惯）。"""
    seen: list[str] = []
    for row in rows:
        for period in row.get("vals") or {}:
            key = str(period)
            if key not in seen:
                seen.append(key)
    return sorted(seen, reverse=True)
