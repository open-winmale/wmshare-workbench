"""``/api/dashboard/run``：每日驾驶舱。

**这一页的硬约束是「不发任何 Manual 级调用」**——它是打开就会跑的首屏，
如果这里挂了付费重请求，用户每开一次工作台都在花钱。对应的验收是
测试断言 ``fetcher.calls`` 里没有任何 ``Manual`` 目标。

四块内容：

1. 指数估值——PE/PB 走 ``cli.index.trend``（末点=最新交易日）；股息率
   只有 ``indices.valuation`` 有，而它是**季度末采样**（current 逐位等于
   最新季末点）——日期如实标注为季度口径。此前整卡只走它，「截至 9-30」
   的根因就是选错了源。
2. 全市场宽度（``screener.index_breadth_summary`` 门面）——涨跌家数/涨停数
3. 资金流前列（``moneyflow.board``）——主力净流入前 N
4. 新鲜度摘要（本地 119 条阈值，零取数）

**不做「今日建议」**：驾驶舱只呈现当天的客观数据，不给结论、不给情绪分。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import as_records, err_from, fetch, int_param
from . import pulse

__all__ = ["handle", "TARGETS", "INDEX_KEYS"]

#: 驾驶舱默认展示的指数（估值表口径；盘面三卡见 ``pulse.PULSE_KEYS``）。
INDEX_KEYS: tuple[str, ...] = ("index.hs300", "index.csi500",
                               "index.sz50", "index.cyb")

#: 本页数据源。**全部是 AUTO 级**（索引聚合/缓存友好），无一 Manual。
TARGETS: dict[str, str] = {
    "valuation": "indices.valuation",
    "trend": "index.trend",
    "breadth": "screener.index_breadth_summary",
    "moneyflow": "moneyflow.board",
    "trading_day": "kline.bars",
}

#: 「最新交易日」的参照指数。宽度/资金流上游**没有任何日期字段**（样例
#: 实证），取沪深300最新一根日 K 的日期作交易日历事实——它是推断口径
#: （「数据属于哪个交易日」上游没说），因此不冒充信封 as_of（行情页同款）。
TRADING_DAY_SYMBOL = "index.hs300"

#: ``index.trend`` 的窗口参数。实测上游 points 恒为 ~10 年采样（window
#: 不改变 points，只影响分位字段），取标准 5y 档即可。
TREND_WINDOW = "5y"


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    limit = int_param(params, "limit", 8, lo=1, hi=30)
    warnings: list[str] = []

    valuation, val_note, indices_as_of, dv_as_of = _valuations(ctx, warnings)
    breadth, breadth_note = _breadth(ctx, warnings)
    flows, flow_note = _flows(ctx, limit, warnings)
    trading_day = _trading_day(ctx)
    cards = pulse.index_cards(ctx, warnings)
    dist = pulse.distribution(ctx, warnings)
    # 推断口径升级（2026-11-26 实测翻车）：指数最新日 K **盘后才物化**，
    # 盘中 trading_day 恒滞后一天，页头「11-25」与盘面三卡「11-26」在
    # 同页打架——实时与非实时混在一个日期口径里。同一批上游中，盘面
    # 快照的日期是更新鲜的事实，取 max。仍是推断（上游不标注）。
    card_dates = [str(c.get("date") or "") for c in cards]
    if any(card_dates):
        trading_day = max([trading_day, *card_dates])

    if not any((valuation, breadth, flows)):
        return err_from(ctx, RuntimeError("驾驶舱三块数据都未取到"))

    return ok_envelope(
        {
            "indices": valuation,
            "index_note": val_note,
            # 今日盘面三大指数卡（现价/涨跌/高低 + 分时 mini，date 守卫
            # 防上游兜底假行）；休市=最近收盘，不冒充盘中跳动
            "index_cards": cards,
            "distribution": dist,
            # PE/PB 的数据日（index.trend 末点日期，最新交易日）——指数卡
            # chip 用；它是 trend 信封里的数据事实
            "indices_as_of": indices_as_of,
            # 股息率与回退口径是**季度末**采样，日期单独给（不与 PE/PB 混）
            "dv_as_of": dv_as_of,
            # 宽度/资金流上游无日期：页级交易日 chip 用推断口径（不提升
            # 为信封 as_of，行情页先例）
            "trading_day": trading_day,
            "breadth": breadth,
            "breadth_note": breadth_note,
            "moneyflow": flows,
            "moneyflow_note": flow_note,
            "index_keys": list(INDEX_KEYS),
            "manual_calls": 0,
        },
        as_of=_as_of(breadth),
        meta={"note": "首屏只发 AUTO 级调用，不含任何付费重请求；"
                      "trading_day 为推断口径（指数最新K线日与盘面快照日期"
                      "取较大者——日 K 盘后才物化，盘中滞后属常态），非上游"
                      "标注；指数分时 mini ~1.6k EC/张（用户拍板首屏直出）",
              "auto_only": True},
        freshness="fresh",
        ec=EcEstimate(model="index_aggregate"),
        warnings=warnings)


def _valuations(ctx: Any,
                warnings: list[str]) -> tuple[list[dict[str, Any]], str,
                                              str, str]:
    """逐个指数取估值 →（行表, note, PE/PB 数据日, 股息率季度末日期）。

    **``0`` 归一成缺失**（上游对未供数字段给 ``0``，估值不可能真是 0）。
    PE/PB 优先 ``index.trend``（末行=最新交易日）；不覆盖的指数回退
    ``indices.valuation`` 季度末 ``current`` 并标 ``quarterly`` 告警——
    **回退口径必须可见**。dv 恒为季度口径（股息率无指数级更新序列）。
    """
    out: list[dict[str, Any]] = []
    missing: list[str] = []
    quarterly: list[str] = []
    dv_dates: list[str] = []
    for key in INDEX_KEYS:
        val = _fetch_valuation(ctx, key)
        fresh = _trend_latest(ctx, key)
        row = _valuation_row(key, fresh, val)
        if row is None:
            missing.append(key)
            continue
        out.append(row)
        _collect_val_dates(val, dv_dates)
        if row.get("quarterly"):
            quarterly.append(str(row["label"]))
    if missing:
        warnings.append(f"指数估值缺：{'、'.join(missing)}")
    if quarterly:
        warnings.append(f"{'、'.join(quarterly)} 无最新交易日估值，"
                        "PE/PB 为季度末口径")
    note = (f"{len(out)}/{len(INDEX_KEYS)} 个指数有估值"
            if out else "无可用指数估值")
    pe_dates = [str(r.get("pe_date") or "") for r in out if r.get("pe_date")]
    return (out, note, (max(pe_dates) if pe_dates else ""),
            (max(dv_dates) if dv_dates else ""))


def _fetch_valuation(ctx: Any, key: str) -> dict[str, Any] | None:
    """``indices.valuation``（季度口径）：dv 唯一来源，也是 PE/PB 的回退。"""
    try:
        raw, _ = fetch(ctx, TARGETS["valuation"], {"key": key})
    except Exception:  # noqa: BLE001 - 单指数失败只降级
        return None
    return raw if isinstance(raw, dict) else None


def _trend_latest(ctx: Any, key: str) -> dict[str, Any] | None:
    """``index.trend`` 最新点 → ``{pe, pb, pe_date}``；失败/不覆盖 → None。

    门面返回**统一信封**（``points`` 在 ``data`` 里）；points 是升序
    DataFrame（date/pe/pb），末行即最新交易日。创业板指实测 0 行
    （该源不覆盖）→ None，由调用方回退季度口径。
    """
    try:
        raw, _ = fetch(ctx, TARGETS["trend"],
                       {"key": key, "window": TREND_WINDOW},
                       facade=("index", "trend"))
    except Exception:  # noqa: BLE001 - 单指数失败只降级
        return None
    data = raw.get("data") if isinstance(raw, dict) else None
    points = data.get("points") if isinstance(data, dict) else None
    rows = as_records(points) if points is not None else []
    if not rows:
        return None
    last = rows[-1]
    return {"pe": last.get("pe"), "pb": last.get("pb"),
            "pe_date": str(last.get("date") or "")[:10]}


def _valuation_row(key: str, fresh: dict[str, Any] | None,
                   val: dict[str, Any] | None) -> dict[str, Any] | None:
    """合并 trend 与季度口径为一行；两路都没有 PE/PB → None（进缺失）。"""
    current = val.get("current") if isinstance(val, dict) else None
    pe = pb = None
    pe_date = ""
    quarterly = False
    if fresh is not None:
        pe = _positive(fresh.get("pe"))
        pb = _positive(fresh.get("pb"))
        pe_date = str(fresh.get("pe_date") or "")
    elif isinstance(current, dict):
        pe = _positive(current.get("pe"))
        pb = _positive(current.get("pb"))
        quarterly = True
    if pe is None and pb is None:
        return None
    dv = current.get("dv") if isinstance(current, dict) else None
    return {"key": key, "label": _INDEX_LABELS.get(key, key),
            "pe": pe, "pb": pb, "dv": _positive(dv),
            "pe_date": pe_date, "quarterly": quarterly}


def _collect_val_dates(val: dict[str, Any] | None, dates: list[str]) -> None:
    """收集 ``series[].d``（季度末，dv 与回退口径的数据日期）。"""
    series = val.get("series") if isinstance(val, dict) else None
    for point in (series or []):
        got = point.get("d") if isinstance(point, dict) else None
        if isinstance(got, str) and got:
            dates.append(got[:10])


def _positive(value: Any) -> float | None:
    """``> 0`` 才有意义；``0`` / ``None`` / 非数字 → ``None``（缺失）。

    估值类字段为 0 只可能是上游「未供数」，把它显示出来会造出一个假的
    极低估值——用户无从分辨这是真数据还是占位。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


_INDEX_LABELS: dict[str, str] = {
    "index.hs300": "沪深300",
    "index.csi500": "中证500",
    "index.sz50": "上证50",
    "index.cyb": "创业板指",
}


def _trading_day(ctx: Any) -> str:
    """最新交易日（沪深300最新一根日 K 的日期）——推断口径。

    **失败不终止页面**：这只是日期参照，取不到就缺省（前端回落
    「截至未知」）。指数仅日频（上游不派生指数周/月 K），``n=1`` 一根。
    """
    try:
        raw, _ = fetch(ctx, TARGETS["trading_day"],
                       {"symbol": TRADING_DAY_SYMBOL, "n": 1},
                       facade=("kline", "bars"))
    except Exception:  # noqa: BLE001 - 日期参照失败只降级
        return ""
    dates = [str(r.get("date") or "")[:10] for r in as_records(raw)]
    dates = [d for d in dates if d]
    return max(dates) if dates else ""


def _breadth(ctx: Any,
             warnings: list[str]) -> tuple[dict[str, Any], str]:
    try:
        # 走组合门面：``kline.index_breadth_summary`` 要求显式 idx，
        # 门面内部用 LatestIndexKey() 自行解析（实测目录函数无 idx 直接失败）
        raw, _ = fetch(ctx, TARGETS["breadth"], {},
                       facade=("screener", "index_breadth_summary"))
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"涨跌全景读取失败：{exc}")
        return {}, "读取失败"
    if not isinstance(raw, dict):
        return {}, "返回结构异常"
    keys = ("up", "down", "flat", "limit_up", "limit_down", "median_pct")
    out = {k: raw.get(k) for k in keys if k in raw}
    if not out:
        return {}, "无可用数据（可能是非交易日）"
    return out, ""


def _flows(ctx: Any, limit: int,
           warnings: list[str]) -> tuple[list[dict[str, Any]], str]:
    try:
        raw, _ = fetch(ctx, TARGETS["moneyflow"], {})
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"资金流读取失败：{exc}")
        return [], "读取失败"
    if not isinstance(raw, list):
        return [], "返回结构异常"
    rows = [r for r in raw if isinstance(r, dict)]
    rows.sort(key=lambda r: -(r.get("net_mf") or 0.0))
    return [{"symbol": r.get("symbol"), "name": r.get("name"),
             "net_mf": r.get("net_mf")}
            for r in rows[:limit]], ""


def _as_of(breadth: dict[str, Any]) -> str:
    """驾驶舱的 ``as_of``：只认宽度数据里的日期（若有）。

    宽度上游（实测样本）无日期字段，所以真实模式下本函数通常返回
    ``""``；页级日期由「最新交易日」推断口径（``trading_day``）承担。
    """
    date = breadth.get("date") if isinstance(breadth, dict) else None
    if isinstance(date, str) and date:
        return date[:10]
    return ""
