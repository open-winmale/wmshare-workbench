"""``/api/markets/run``：行情表与 KPI。

与「自选」的分工：自选是**你关心的几只**，行情是**全市场的概览**。
所以这一页取的是宽度（涨跌家数）、涨跌榜、板块资金流，而不是逐票表格。

**数值排序键独立于显示文本**（``DESIGN_SYSTEM`` §4）：这里返回的
``percent`` 是小数（0.0175），前端格式化成 ``+1.75%`` 显示，但排序用原值。
如果把 ``+1.75%`` 当字符串排，``+10%`` 会排在 ``+9%`` 前面。

**宽度三件套必须走组合门面**（``cli.screener.index_*``），不能走
``kline.index_*`` 目录函数：后者要求显式 ``idx``（不传就报「缺少必填参数」），
而门面内部用 ``LatestIndexKey()`` 自行解析最新索引。实测 ``kline.index_breadth_summary``
在无 idx 时直接失败——这是本页在真实模式下白屏的根因。

**返回值可能是 DataFrame 也可能是 list**：门面在服务端聚合路径返回
DataFrame，直读路径返回 list。``as_records``（`tools/_shared`）统一成
list[dict]，否则前端在真实模式下拿到 ``.length === undefined`` 会整页空白。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import as_records, err_from, fetch, int_param, str_param

__all__ = ["handle", "TARGETS", "FACADES"]

#: 数据源（目录函数名，仅作缓存键与展示）。
TARGETS: dict[str, str] = {
    "breadth": "screener.index_breadth_summary",
    "bins": "screener.index_breadth_bins",
    "movers": "screener.index_top_movers",
    "moneyflow": "moneyflow.board",
}

#: 组合门面：宽度三件套必须走 ``cli.screener.*``（内部解析最新索引）。
FACADES: dict[str, tuple[str, str]] = {
    "breadth": ("screener", "index_breadth_summary"),
    "bins": ("screener", "index_breadth_bins"),
    "movers": ("screener", "index_top_movers"),
}

#: 「最新交易日」的参照指数。宽度/资金流上游**没有任何日期字段**（样例
#: 实证），取沪深300最新一根日 K 的日期作交易日历事实——它是推断口径
#: （「数据属于哪个交易日」上游没说），因此不冒充信封 as_of。
TRADING_DAY_SYMBOL = "index.hs300"


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    idx = str_param(params, "idx")
    limit = int_param(params, "limit", 10, lo=1, hi=50)
    try:
        breadth, _ = fetch(ctx, TARGETS["breadth"], _idx_params(idx),
                           facade=FACADES["breadth"])
        bins, _ = fetch(ctx, TARGETS["bins"], _idx_params(idx),
                        facade=FACADES["bins"])
        movers, as_of = fetch(ctx, TARGETS["movers"],
                              {**_idx_params(idx), "limit": limit, "desc": True},
                              facade=FACADES["movers"])
        flows, _ = fetch(ctx, TARGETS["moneyflow"], {})
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    summary = _summary(breadth)
    return ok_envelope(
        {
            "kpi": summary,
            "breadth": _normalize(breadth),
            "bins": _bins(bins),
            "movers": _movers(movers),
            "moneyflow": _flows(flows, limit),
            "trading_day": _trading_day(ctx),
            "sources": list(TARGETS.values()),
        },
        as_of=as_of,
        meta={"note": "宽度与资金流由服务端索引聚合直出，未在客户端重算；"
                      "trading_day 为推断口径（指数最新K线日），非上游标注"},
        freshness="fresh",
        ec=EcEstimate(model="index_aggregate"),
        warnings=_breadth_warnings(summary))


def _trading_day(ctx: Any) -> str:
    """最新交易日（沪深300最新一根日 K 的日期）。

    **失败不终止页面**：这只是日期参照，取不到就缺省（前端回落
    「截至未知」）。指数仅日频（上游不派生指数周/月 K），``n=1`` 一根。
    """
    try:
        raw, _ = fetch(ctx, "kline.bars",
                       {"symbol": TRADING_DAY_SYMBOL, "n": 1},
                       facade=("kline", "bars"))
    except Exception:  # noqa: BLE001 - 日期参照失败只降级
        return ""
    dates = [str(r.get("date") or "")[:10] for r in as_records(raw)]
    dates = [d for d in dates if d]
    return max(dates) if dates else ""


def _idx_params(idx: str) -> dict[str, Any]:
    """``idx`` 只有显式给了才传——传空串会让服务端解析失败。"""
    return {"idx": idx} if idx else {}


def _summary(raw: Any) -> dict[str, Any]:
    """涨跌全景。占比一律小数（服务端 2.0 起已统一）。"""
    if not isinstance(raw, dict):
        return {}
    keys = ("up", "down", "flat", "limit_up", "limit_down",
            "up_pct", "down_pct", "flat_pct", "median_pct")
    return {k: raw.get(k) for k in keys if k in raw}


def _normalize(raw: Any) -> dict[str, Any]:
    """宽度原始行（保留全部字段，供「展开原始数据」用）。"""
    return raw if isinstance(raw, dict) else {}


def _bins(raw: Any) -> list[dict[str, Any]]:
    """涨跌幅分桶。``count`` 必须保留为数字（不能变成字符串）。"""
    out: list[dict[str, Any]] = []
    for row in as_records(raw):
        label = row.get("bin") or row.get("label") or row.get("name") or ""
        out.append({"bin": str(label), "count": row.get("count")})
    return out


def _movers(raw: Any) -> list[dict[str, Any]]:
    return [{"symbol": r.get("symbol"), "name": r.get("name"),
             "percent": r.get("percent")}
            for r in as_records(raw)]


def _flows(raw: Any, limit: int) -> list[dict[str, Any]]:
    """主力净流入前 N（按 ``net_mf`` 降序）。

    **按净额排，不按 ``net_mv_ratio``**：后者是相对市值强度，与「谁被
    最多钱买」是两件不同的事。混用会让小盘股永远排在前面。
    """
    rows = as_records(raw)
    rows.sort(key=lambda r: -(r.get("net_mf") or 0.0))
    return [{"symbol": r.get("symbol"), "name": r.get("name"),
             "net_mf": r.get("net_mf"), "net_mv_ratio": r.get("net_mv_ratio"),
             "elg_net": r.get("elg_net"), "lg_net": r.get("lg_net")}
            for r in rows[:limit]]


def _breadth_warnings(summary: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if summary.get("up") is not None and summary.get("down") is not None:
        total = (summary.get("up") or 0) + (summary.get("down") or 0) \
            + (summary.get("flat") or 0)
        if total <= 0:
            out.append("涨跌家数为 0：可能是非交易日，或索引尚未物化")
    return out
