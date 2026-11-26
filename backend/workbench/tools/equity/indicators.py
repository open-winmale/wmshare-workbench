"""主要财务指标（``cli.statements.indicators``）。

**为什么它排在财务报表的第一位**：实务上看财报第一步是看主要指标
（营收/净利/ROE/毛利率/EPS），而不是直接翻 52 行科目明细。默认落在
科目明细上等于让用户自己去几百个数字里找重点。

**数据来源与两条路的区别**（踩过）：

- ``cli.statements.indicators()`` 走 SDK **门面**（内部 ``build_statement_xs``
  + ``eval_result``），返回 ``k`` / ``cn`` / ``vals``，49 个指标 × 各期。
  免注册下**可用**（实测）。
- ``rptdom.statement`` 的 ``domain`` **不含** ``fin.indicator*``——传进去会
  「不在允许值」。所以指标表必须走门面，不能走目录函数。

**``cn`` 不可信**：上游把 ``cn`` 填成了 ``k`` 的副本（``basicEps``、
``grossProfitRatio``），不是中文名。因此本模块自己维护中文名映射，
**只映射确认过的指标**；未登记的原样显示 key——不猜中文名，猜错比英文更难发现。
"""

from __future__ import annotations

from typing import Any

from ...tools._shared import ToolError, as_records, fetch

__all__ = ["build", "INDICATOR_LABELS", "PRIMARY_INDICATORS"]


#: 指标 key → (中文名, 口径)。**只列确认过语义的**。
#: 口径：``money`` 元 · ``pct`` 小数 · ``num`` 数值 · ``days`` 天 · ``ratio`` 倍数
INDICATOR_LABELS: dict[str, tuple[str, str]] = {
    "totalOperatingIncome": ("营业总收入", "money"),
    "deduParentProfit": ("归母净利润", "money"),
    "roe": ("净资产收益率 ROE", "pct"),
    "grossProfitRatio": ("毛利率", "pct"),
    "netProfitRatio": ("净利率", "pct"),
    "basicEps": ("基本每股收益", "num"),
    "dilutedEps": ("稀释每股收益", "num"),
    "equityRatio": ("产权比率", "pct"),
    "totalAssetTr": ("总资产周转率", "num"),
    "inventoryTr": ("存货周转率", "num"),
    "xjllb": ("现金流量比率", "num"),
    "totalAssetTdays": ("总资产周转天数", "days"),
}

#: 首屏展示的「主要指标」顺序 —— 按分析时的阅读顺序排：
#: 规模 → 盈利 → 质量 → 每股 → 效率。其余指标折叠在「全部指标」里。
PRIMARY_INDICATORS: tuple[str, ...] = (
    "totalOperatingIncome", "deduParentProfit",
    "roe", "grossProfitRatio", "netProfitRatio",
    "basicEps", "dilutedEps",
    "equityRatio", "totalAssetTr", "inventoryTr", "xjllb", "totalAssetTdays",
)


def build(ctx: Any, symbol: str,
          params: dict[str, Any]) -> tuple[Any, str, list[str]]:
    """主要指标（跨期）。走门面——公开门面四表都支持 ``period`` 档位。"""
    period = _period(params)
    raw, as_of = fetch(ctx, "statements.indicators",
                       {"symbol": symbol, "years": 5, "period": period},
                       facade=("statements", "indicators"))
    rows = _as_rows(raw)
    if not rows:
        raise ToolError(f"{symbol} 无主要指标数据", code="upstream",
                        action="retry")
    periods = _periods(rows)
    labelled = [_label(row) for row in rows]
    # 首屏指标按 PRIMARY_INDICATORS 顺序置前，其余保持上游顺序
    order = {k: i for i, k in enumerate(PRIMARY_INDICATORS)}
    labelled.sort(key=lambda r: (order.get(str(r["k"]), len(order)),
                                 str(r["k"])))
    return ({"period": period, "periods": periods, "rows": labelled,
             "primary": list(PRIMARY_INDICATORS)}, as_of, [])


def _period(params: dict[str, Any]) -> str:
    """报告期档位：``annual``（年报档）/ ``quarter``（季报累计档 Q1..Q4）。"""
    value = str(params.get("period") or "annual")
    if value not in ("annual", "quarter"):
        raise ToolError(f"period 只支持 annual/quarter，收到 {value!r}",
                        code="param")
    return value


def _as_rows(raw: Any) -> list[dict[str, Any]]:
    """归一成 ``[{k, vals}]``。

    形状归一交给 ``tools._shared.as_records``（唯一实现）；这里只做**业务过滤**：
    没有跨期 ``vals`` 的行不是指标行。
    """
    out: list[dict[str, Any]] = []
    for row in as_records(raw):
        vals = row.get("vals")
        if isinstance(vals, dict):
            out.append({"k": row.get("k"), "vals": vals})
    return out


def _periods(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        for period in row.get("vals") or {}:
            key = str(period)
            if key not in seen:
                seen.append(key)
    return sorted(seen, reverse=True)


def _label(row: dict[str, Any]) -> dict[str, Any]:
    """补中文名与口径。未登记的**原样保留 key**（不猜）。"""
    key = str(row.get("k") or "")
    label, fmt = INDICATOR_LABELS.get(key, (key, "num"))
    return {"k": key, "label": label, "format": fmt, "vals": row["vals"]}
