"""形状夹具（测试专用） —— 按参数收窄的处理器（通用范式）。

这里放的是「同一个 target、不同参数 → 不同数据」的规则。**这些规则
值得单独一个文件**，因为它们承载的都是踩过的坑：

- 未知指标码返回**空序列**而不是假数据（假数据会掩盖「码拼错」）
- 批量快照里**未收录的代码不出现**（真实服务端只返回它有数据的标的；
  这里若替它编一份，前端就永远看不到「缺数据」这条路径）
- 指数估值**每只必须不同**（全相同会让「指数间无差异」看起来像事实）
- 债券曲线**各期限不同**（全平会让「曲线是平的」看起来像数据事实）

``shape_data`` 只负责装配与分发，收窄逻辑在这里和数据族（``shape_gen`` /
``shape_extra``）里。
"""

from __future__ import annotations

from typing import Any

from shape_gen import ANCHOR_DATE, SHAPE_SYMBOLS, _bars, _index_valuation, _snapshot

__all__ = [
    "shape_bond_curve",
    "shape_index_min1_live",
    "shape_index_trend",
    "shape_index_valuation",
    "shape_last_live",
    "shape_live_many",
    "shape_macro_query",
    "shape_min1_live",
    "shape_per_symbol",
    "shape_statement_rows",
    "shape_top_movers",
]

#: 可按标的收窄的 target（切标的时数据要跟着变，否则演示会露馅）。
PER_SYMBOL_TARGETS: tuple[str, ...] = (
    "kline.snapshot", "kline.query_bars", "kline.query_bars_adj",
    "kline.bars",
)

#: 演示可用的宏观指标码（与 ``tools/economics`` 的选择器一致）。
KNOWN_MACRO_CODES: frozenset[str] = frozenset({
    "$CPI", "$PPI", "$M1", "$M2", "$GDP", "$PMI",
})

#: 国债曲线各期限（**必须各不相同**：全期限同一个数会让「曲线是平的」
#: 看起来像数据事实，而实际上那只是形状夹具（测试专用）没做完）。
BOND_CURVE: dict[str, float] = {
    "1年": 0.0125, "3年": 0.0142, "5年": 0.0158,
    "7年": 0.0165, "10年": 0.0168, "30年": 0.0193,
}

#: 形状夹具（测试专用）表（由 ``shape_data`` 注入，避免这里再构造一遍）。
_TABLE: dict[str, Any] = {}


def bind(table: dict[str, Any]) -> None:
    """绑定形状夹具（测试专用）表。**由 ``shape_data`` 在模块加载后调用一次**。"""
    _TABLE.clear()
    _TABLE.update(table)


def shape_per_symbol(target: str, params: dict[str, Any]) -> Any:
    """按 ``sym``/``symbol`` 收窄。未收录代码造一份**形状正确**的。

    ``sym`` 传**列表**时返回整表——真实 ``kline.snapshot`` 批量路由按量
    投影，但 handler 本来就只取自己要的键，整表不会外泄多余行。
    """
    value = _TABLE[target]
    sym = params.get("sym") or params.get("symbol")
    if not isinstance(sym, str) or not sym:
        return value
    if sym in value:
        return value[sym]
    return _bars(sym) if "bars" in target else _make_snapshot(sym)


def shape_live_many(params: dict[str, Any]) -> Any:
    """live_many 按请求的 ``syms`` 收窄。未收录的代码不出现在返回里
    ——与真实服务端一致（缺数据这条路径必须可见）。"""
    syms = params.get("syms") or []
    table = _TABLE["kline.query_last_live_many"]
    if not syms:
        return table
    return {s: table[s] for s in syms if s in table}


def shape_top_movers(params: dict[str, Any]) -> Any:
    rows = _TABLE["screener.index_top_movers"]
    limit = int(params.get("limit") or len(rows))
    if not params.get("desc", True):
        rows = list(reversed(rows))
    return rows[:limit]


def shape_macro_query(params: dict[str, Any]) -> Any:
    """宏观时序。**未知指标码返回 value 全 None 的骨架点**，与真实一致
    （真实上游不报错，给扁平骨架、新→旧；handler 把它归为「无可用值」
    而不是让「码拼错」看起来像有数据）。已知的按 ``n`` 收窄（新→旧取前
    n 个，与真实服务端行为一致）。"""
    code = str(params.get("code") or "").upper()
    table = _TABLE["macro.query"]
    if code not in KNOWN_MACRO_CODES:
        skeleton = {"annual": 2026, "sampling": "M10", "sas": "2026:M10",
                    "value": None}
        return {**table, "metric": code, "store": "", "periods": 1,
                "latest": skeleton, "series": [dict(skeleton)]}
    n = int(params.get("n") or 0)
    rows = table.get("series") or []
    if n:
        rows = rows[:n]
    return {**table, "periods": len(rows), "series": rows}


def shape_bond_curve(params: dict[str, Any]) -> Any:
    """收益率曲线：按期限给不同的值；未知期限返回 ``None``（不造点）。"""
    tenor = str(params.get("tenor") or "")
    value = BOND_CURVE.get(tenor)
    if value is None:
        return None
    return {"curve_name": str(params.get("curve_name") or ""),
            "tenor": tenor, "value": value}


def shape_index_valuation(params: dict[str, Any]) -> Any:
    key = str(params.get("key") or "")
    known = (
        "index.hs300", "index.csi500", "index.sz50", "index.cyb", "index.zz500",
    )
    return _index_valuation(key if key in known else "index.hs300")


def shape_min1_live(params: dict[str, Any]) -> Any:
    """分时按 ``sym`` 收窄。未收录代码给 **bar_n=0 的空载荷**（形状正确）：
    真实源对无覆盖标的就不给点数，handler 归「暂无分时」而不是编数据。"""
    table = _TABLE["kline.query_min1_live"]
    sym = params.get("sym")
    if isinstance(sym, str) and sym in table:
        return table[sym]
    return {"bar_n": 0, "bars": [], "market": "cn",
            "symbol": str(sym or ""), "trading_day": "", "updated_at": ""}


def shape_index_min1_live(params: dict[str, Any]) -> Any:
    """指数分时按 ``key`` 收窄（与个股分时同形，2026-11-26 实测）。未收录
    的指数键给 **bar_n=0 空载荷**：真实源不覆盖的键就是空的（创业板指
    多个估值源皆如此），回退路径必须在演示里走得通。"""
    table = _TABLE["kline.query_index_min1_live"]
    key = params.get("key")
    if isinstance(key, str) and key in table:
        return table[key]
    return {"bar_n": 0, "bars": [], "market": "cn",
            "symbol": str(key or ""), "trading_day": "", "updated_at": ""}


def shape_last_live(params: dict[str, Any]) -> Any:
    """单票盘中快照按 ``sym`` 收窄。未收录代码给 ``None``——真实上游对
    无覆盖标的返回 ``None``（实测 999999）；ETF 返回 ``{"ok": false,
    "code": "unsupported"}`` 的 dict（同为「无」），handler 两样都兜。"""
    table = _TABLE["kline.query_last_live"]
    sym = params.get("sym")
    if isinstance(sym, str) and sym in table:
        return table[sym]
    return None


def shape_index_trend(params: dict[str, Any]) -> Any:
    """指数周频估值（``cli.index.trend`` **统一信封**形状）。

    ``points`` 升序（date/pe/pb），末行=最新交易日——真实门面如此，
    驾驶舱取末行当 PE/PB 数据日。未收录的指数给**空 points**：真实源
    不覆盖创业板指（0 行），季度回退路径必须在演示里走得通。
    """
    key = params.get("key")
    table = _TABLE["index.trend"]
    if isinstance(key, str) and key in table:
        return table[key]
    return {"ok": True, "as_of": "", "data": {"key": key, "points": []},
            "meta": {}}


def _make_snapshot(sym: str) -> dict[str, Any]:
    """未收录代码的兜底快照（**形状正确**，不是空对象）。"""
    return _snapshot(sym, f"标的{sym}", 20.0, 0.001, "industry.S00")


def shape_statement_rows(target: str, params: dict[str, Any]) -> Any:
    """报表/指标按 ``period`` 变形：annual=原样（年份键），quarter=季报累计档。

    真实季报档的期次键是 ``YYYY-Qn``（``indicators(period='quarter')`` 实测
    ``2026-Q2/2026-Q3``），给最近 5 个**已披露**季报（锚点所在季度的报告
    还没出，从上一季往回数）；值按累计口径从同年度报值递推（Q1=25%、
    Q2=50%、Q3=75%、Q4=100%）——演示值本就是编的，形状对齐才是 D-27 的要求。
    """
    rows = _TABLE.get(target)
    if not isinstance(rows, list):
        return rows
    if (params.get("period") or "annual") != "quarter":
        return rows
    return _quarterize(rows)


def _recent_quarters(count: int) -> list[str]:
    """截至锚点的最近 ``count`` 个**已披露**季报标签（新→旧，``YYYY-Qn``）。

    锚点所在季度的报告尚未披露（11-20 → Q4 报告次年才出），从上一季起算。
    """
    year, quarter = ANCHOR_DATE.year, (ANCHOR_DATE.month - 1) // 3 + 1
    quarter -= 1
    if quarter == 0:
        year, quarter = year - 1, 4
    out = []
    for _ in range(count):
        out.append(f"{year}-Q{quarter}")
        quarter -= 1
        if quarter == 0:
            year, quarter = year - 1, 4
    return out


def _quarterize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quarters = _recent_quarters(5)
    frac = {"Q1": 0.25, "Q2": 0.5, "Q3": 0.75, "Q4": 1.0}
    out: list[dict[str, Any]] = []
    for row in rows:
        vals = row.get("vals") if isinstance(row.get("vals"), dict) else {}
        years = sorted((k for k in vals if k.isdigit()), reverse=True)
        latest = vals.get(years[0]) if years else None
        qvals: dict[str, Any] = {}
        for q in quarters:
            base = vals.get(q[:4], latest)
            if isinstance(base, (int, float)) and not isinstance(base, bool):
                qvals[q] = round(base * frac[q[5:]], 4)
        out.append({**row, "vals": qvals})
    return out


#: 供 ``shape_data`` 校验演示标的集合（避免两处各写一份）。
SYMBOLS: tuple[str, ...] = SHAPE_SYMBOLS
