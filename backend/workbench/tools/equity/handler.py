"""``/api/equity/run``：个股研究（分区懒加载）。

**为什么是分区而不是一次全拉**：一个标的的「三表 + 估值序列 + 分红 + 预测」
全拉一遍是十几万 EC 量级。打开研究页的第一步只是想看个大概，因此默认区
（``overview``）只取快照 + 估值当前值；三表与分红序列要用户点开才取。

**``decomp`` 默认不可见且成本极高**：实测（2026-11-25，免注册池）5 年档
热态 15,814 EC、10 年档热态 328,857 EC、冷态首查（AT 锚点物化惩罚）可达
721,953 EC。它只在显式请求 ``section=decomp`` 时出现，且必须在 UI 上标出
成本量级——**成本随年限超线性增长**，所以默认年限取 5 而非 10。

**这一页不产出结论**：不给目标价、不给评级、不给「值不值得买」。
只把公开数据按分区摊开。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import ToolError, err_from, fetch, int_param, str_param
from . import decomp
from .bars import build as build_bars
from .bars import build_minute as build_minute
from .decomp import build as build_decomp
from .dividend import build as build_dividend
from .forecast import build as build_forecast
from .statements import build as build_statements

__all__ = ["handle", "SECTIONS", "DEFAULT_SECTION", "EXPENSIVE_SECTIONS"]

#: 可用分区 → (展示名, 简述)。
SECTIONS: dict[str, dict[str, str]] = {
    "overview": {"title": "概览", "note": "快照 + 盘中现价 + TTM 股息率"},
    "bars": {"title": "行情走势", "note": "日 K 线 + 成交量（20–500 个交易日）"},
    "minute": {"title": "分时", "note": "当日 1 分钟分时（盘中实时，休市=最近交易日）"},
    "valuation": {"title": "估值序列", "note": "每日 PE/PB/PS/PR 序列"},
    "statements": {"title": "财务报表",
                   "note": "主要指标 → 利润表 / 资产负债表 / 现金流量表"},
    "dividend": {"title": "分红", "note": "TTM 股息率、派息率、3 年趋势与历史明细"},
    "decomp": {"title": "持有收益拆解",
               "note": "按持有年限拆分价格与股息贡献"},
    "forecast": {"title": "业绩预告", "note": "预告 / 快报 / 下次预约披露"}
}

DEFAULT_SECTION = "overview"

#: 需要显式请求的高成本分区（不在默认区出现）。
#: 2026-11-25 用户拍板：拆解不再确认、直接加载（成本提示一并移除），
#: 此集合暂空；机制保留给未来真正需要二次确认的分区。
EXPENSIVE_SECTIONS: frozenset[str] = frozenset()


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    try:
        symbol = str_param(params, "symbol")
        if not symbol:
            raise ToolError("缺少标的代码（symbol）", code="missing_param")
        section = str_param(params, "section") or DEFAULT_SECTION
        if section not in SECTIONS:
            raise ToolError(f"未知分区 {section!r}；可选 "
                            f"{'/'.join(SECTIONS)}", code="param")
        if section in EXPENSIVE_SECTIONS and not params.get("confirmed"):
            return _confirm_cost(ctx, symbol, section, params)
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    build = _BUILDERS.get(section)
    if build is None:
        return err_from(ctx, ToolError(f"分区 {section} 尚未实现",
                                       code="not_ready", action="config"))
    try:
        payload, as_of, warnings = build(ctx, symbol, params)
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    return ok_envelope(
        {
            "symbol": symbol,
            "section": section,
            "sections": [{"key": k, **v, "expensive": k in EXPENSIVE_SECTIONS}
                         for k, v in SECTIONS.items()],
            "data": payload,
        },
        as_of=as_of,
        meta={"note": "分区懒加载：打开只取概览；本页不产出投资结论"},
        freshness="fresh",
        ec=_section_ec(ctx),
        warnings=warnings)


def _section_ec(ctx: Any) -> EcEstimate:
    """分区级成本标签。

    具体分区的 ``pred_*`` 由 ``FakeFetcher``（``None``）或 SDK 的成本模型给；
    这里只标注「按分区计价」这一口径。**不按访问方式打标**——那会让
    「有真实成本模型」与「没有」混成一个标签。
    """
    return EcEstimate(model="per_section")


def _confirm_cost(ctx: Any, symbol: str, section: str,
                  params: dict[str, Any]) -> dict[str, Any]:
    """高成本分区：返回确认请求，**不发任何上游调用**。

    确认框里给**具体年限对应的成本区间**，而不是「数十万」这种笼统说法：
    用户要做的是「要不要花这笔钱」的决定，需要的是数字。成本模型来自
    ``fetcher.cost_estimate``（SDK 侧 ``measured`` 模型），无模型时如实
    显示「未知」而**不是 0**。
    """
    estimate = _section_estimate(ctx, symbol, section, params)
    return ok_envelope(
        {
            "symbol": symbol,
            "section": section,
            "needs_confirm": True,
            "expensive": True,
            "estimate": estimate,
            "message": _cost_message(section, estimate),
            "sections": [{"key": k, **v, "expensive": k in EXPENSIVE_SECTIONS}
                         for k, v in SECTIONS.items()],
        },
        as_of="",
        meta={"note": "等待用户确认", "zero_requests": True},
        freshness="unknown",
        ec=_section_ec(ctx))


#: 会自行回答「这次要花多少」的分区。查成本模型属于分区自己的知识——
#: 放在 handler 里会让 handler 认识每个分区的上游 target，那是分区的私事。
_SECTION_COST = {"decomp": (decomp.estimate, decomp.cost_message)}


def _section_estimate(ctx: Any, symbol: str, section: str,
                      params: dict[str, Any]) -> dict[str, Any]:
    """按本次请求的参数查成本模型。**不写死数字**——年限变了成本就变。"""
    handler = _SECTION_COST.get(section)
    if handler is None:
        return {"known": False, "note": "该分区没有成本模型"}
    return handler[0](ctx, symbol, params)


def _cost_message(section: str, estimate: dict[str, Any]) -> str:
    """确认提示：分区自己决定措辞（有模型给区间，无模型说「未知」）。"""
    handler = _SECTION_COST.get(section)
    title = SECTIONS[section]["title"]
    if handler is None:
        return (f"{title} 属于高成本分区；该请求没有成本模型可预估。"
                f"确认后才会发起请求（当前零请求）。")
    return handler[1](estimate, title)


# --------------------------------------------------------------------------
# 各分区
# --------------------------------------------------------------------------

def _overview(ctx: Any, symbol: str,
              params: dict[str, Any]) -> tuple[Any, str, list[str]]:
    """概览：行情快照 + 盘中现价 + 分红摘要。三块独立容错。

    快照（``kline.snapshot``）是**上一已完成交易日**的收盘——盘中打开
    本页，页顶会停在昨天。所以再并一笔 ``kline.query_last_live``（盘中
    快照，休市=最近收盘）：live 日期**严格新于**快照日才覆盖现价并标
    「实时」（语义同自选页）。分红走 ``bonus.snapshot``（返回 dict，18
    字段），**不用** ``bonus.snapshot_yield_ttm``——后者返回**裸 float**，
    按 dict 处理会静默得到 ``{}``，页面上就显示「TTM 股息率 —」，而数据
    其实完全可用。
    """
    warnings: list[str] = []
    snapshot: dict[str, Any] = {}
    dividend: dict[str, Any] = {}
    as_of = ""
    try:
        raw, as_of = fetch(ctx, "kline.snapshot", {"sym": symbol})
        if isinstance(raw, dict):
            # **必须浅拷贝**：hub 缓存的是取数对象本身（连同首次算好的
            # as_of 二元组），合并会原地写 live/kline_date——直接改缓存
            # 会把第一笔的结果烤进后续所有请求（实测：第 1 次 as_of=今天，
            # 第 2 次起退回冻结的旧值）
            snapshot = dict(raw)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"行情快照读取失败：{exc}")
    try:
        raw, _ = fetch(ctx, "bonus.snapshot", {"sym": symbol})
        if isinstance(raw, dict):
            dividend = raw
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"分红快照读取失败：{exc}")
    live_date = _merge_live_quote(ctx, symbol, snapshot, warnings,
                                  force=bool(params.get("force")))
    if live_date:
        as_of = live_date
    if not snapshot and not dividend:
        raise ToolError(f"{symbol} 的概览数据全部未取到", code="upstream",
                        action="retry")
    return ({"snapshot": snapshot, "dividend": dividend}, as_of, warnings)


def _merge_live_quote(ctx: Any, symbol: str, snapshot: dict[str, Any],
                      warnings: list[str], *,
                      force: bool = False) -> str:
    """并一笔盘中快照进概览 → 返回生效的 live 日期（未生效给 ``""``）。

    覆盖语义与自选页一致：live 日期**严格新于**快照 ``kline_date`` 才
    覆盖（相等=同一份数据不标，更早=停牌票旧快照，现价不能倒回）。
    ``force`` 由前端「刷新」透传（绕 hub TTL 直取）。快照/分红不 force
    ——那是慢变档案，TTL 缓存正是为它们设计的。
    （第 2 处 live 合并；第 3 处出现时再提取公共。）
    """
    live = _fetch_live_quote(ctx, symbol, warnings, force=force)
    if not live:
        return ""
    live_date = str(live["date"])[:10]
    if not snapshot:
        # 快照失败但 live 有数：用 live 撑起最小现价块（无 name/industry
        # 等档案字段，头部回落显示代码——比整页报错诚实）
        snapshot.update({"close": live["close"], "percent": live.get("percent"),
                         "mv": live.get("mv"), "kline_date": live_date,
                         "live": True})
        return live_date
    if live_date <= str(snapshot.get("kline_date") or "")[:10]:
        return ""
    for key in ("close", "percent", "amount", "mv"):
        if live.get(key) is not None:
            snapshot[key] = live[key]
    snapshot["kline_date"] = live_date
    snapshot["live"] = True
    return live_date


def _fetch_live_quote(ctx: Any, symbol: str, warnings: list[str], *,
                      force: bool = False) -> dict[str, Any]:
    """取盘中快照，兜住 **2026-11-26 实测的三种「无」形状**：异常（转
    告警）；ETF 的 ``{"ok": false, "code": "unsupported", "message": ...}``
    dict（**不是异常**，转告警）；无覆盖的 ``None``。正常给 18 字段 dict
    （``close/percent/change/mv/date/asof/...``，percent 为小数）。"""
    try:
        raw, _ = fetch(ctx, "kline.query_last_live", {"sym": symbol},
                       force=force)
    except Exception as exc:  # noqa: BLE001 - 实时是增补块，失败不拖垮概览
        warnings.append(f"盘中现价读取失败：{exc}")
        return {}
    if not isinstance(raw, dict) or raw.get("close") is None or not raw.get("date"):
        if isinstance(raw, dict) and raw.get("ok") is False:
            warnings.append("无盘中快照："
                            f"{raw.get('message') or raw.get('code') or '上游不支持'}")
        return {}
    return raw


def _valuation(ctx: Any, symbol: str,
               params: dict[str, Any]) -> tuple[Any, str, list[str]]:
    """估值序列（长表 → 按字段分组，保持日期升序）。"""
    days = int_param(params, "days", 90, lo=10, hi=730)
    raw, as_of = fetch(ctx, "valuation.daily_basic",
                       {"symbol": symbol, "begin": "", "end": ""})
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, list):
        raise ToolError(f"{symbol} 无估值序列", code="upstream", action="retry")
    series: dict[str, list[dict[str, Any]]] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        field = str(row.get("field") or "")
        if not field:
            continue
        series.setdefault(field, []).append({"date": row.get("date"),
                                             "value": row.get("value")})
    for points in series.values():
        points.sort(key=lambda p: str(p.get("date") or ""))
        del points[:-days]
    meta = raw.get("meta") if isinstance(raw, dict) else {}
    return ({"series": series,
             "fields": sorted(series),
             "window": (meta or {}).get("window") or {}},
            as_of, [])


#: 分区 → 构造函数。新增分区同时改 ``SECTIONS`` 与本表。
_BUILDERS = {
    "overview": _overview,
    "bars": build_bars,
    "minute": build_minute,
    "valuation": _valuation,
    "statements": build_statements,
    "dividend": build_dividend,
    "decomp": build_decomp,
    "forecast": build_forecast,
}
