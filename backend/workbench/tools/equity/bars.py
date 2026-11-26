"""「行情走势」「分时」分区：日 K 线 + 成交量、当日 1 分钟分时。

**这是整个工作台第一张价格图**（此前只有 PE/PB 折线与净值曲线）——研究
一只票的第一步是看价格怎么走的，这一步此前在工具里是缺失的（D-16 触发）。

**契约实测过才写代码**（2026-11-25/26，真实模式）：

- ``kline.query_bars(sym, limit)`` 与 ``kline.query_min1_live(sym)`` 都是
  **目录函数**（``client.call()`` 直达，不是组合门面）；
- 日 K 行字段 ``{date, open, high, low, close, volume, amount, percent,
  sas}``，**日期新→旧**（图表需要旧→新，归一在 ``normalize_bars``）；
- ``limit`` = 返回条数（不是日期窗口）——停牌日天然缺席，如实显示；
- 分时真实返回**扁平 dict** ``{bar_n, bars, market, symbol, trading_day,
  updated_at}``，bars 升序分钟点 ``{t "HH:MM", hm, close(现价), volume,
  amount, n, source}``（2026-11-26 盘中实测 ~1.6k EC/次，仅用户点击分区
  时发）；休市返回最近交易日的全天分时——``trading_day`` 如实标注。

分区顺序在「概览」之后：「行情走势」（日 K）→「分时」→「估值序列」。
"""

from __future__ import annotations

from typing import Any

from .._shared import ToolError, fetch, int_param, normalize_bars

__all__ = ["build", "build_minute", "DEFAULT_DAYS"]

DEFAULT_DAYS = 120


def build(ctx: Any, symbol: str, params: dict[str, Any]) -> tuple[dict[str, Any], str, list[str]]:
    """取最近 ``days`` 个交易日的日 K。返回（载荷, as_of, warnings）。"""
    days = int_param(params, "days", DEFAULT_DAYS, lo=20, hi=500)
    raw, _ = fetch(ctx, "kline.query_bars", {"sym": symbol, "limit": days})
    bars, skipped = normalize_bars(raw)
    if not bars:
        raise ToolError(
            f"{symbol} 没有取到任何日 K（可能未上市或上游无覆盖）", code="upstream", action="retry"
        )
    # 真实数据恰好 limit 条；演示数据忽略 limit 给整段 60 根——这里再裁
    # 一次让两种模式行为一致（多裁无害：len(bars) <= days 时是空切片）
    del bars[:-days]
    warnings: list[str] = []
    if skipped:
        warnings.append(f"{skipped} 行缺少开高低收，未绘制（缺失不补 0）")
    payload = {
        "bars": bars,
        "count": len(bars),
        "days": days,
        "first_date": bars[0]["date"],
        "last_date": bars[-1]["date"],
    }
    # 信封 as_of 用**最新一根**K 线的日期：上游返回新→旧，fetch 的
    # as_of_of 取 [-1] 会拿到最旧一天（见 normalize_bars 注释）
    return payload, str(bars[-1]["date"]), warnings


def build_minute(ctx: Any, symbol: str,
                 params: dict[str, Any]) -> tuple[dict[str, Any], str, list[str]]:
    """当日 1 分钟分时。空分时给 ``intraday: False`` + **原因化 note**，
    **不回退日 K**——用户要的是分时，悄悄换图等于骗点击；把「指数没有
    分钟源」说成「未开盘」同样骗人（2026-11-26 用户实测撞上）。

    ``force``：绕过 hub 缓存直取上游（前端「刷新」用）——分时是用户主动
    要「此刻」的数据，30 秒缓存里的旧「更新于」会让人以为刷新没生效。
    """
    target, fetch_params = _minute_target(symbol)
    try:
        raw, _ = fetch(ctx, target, fetch_params,
                       force=bool(params.get("force")))
    except Exception as exc:  # noqa: BLE001 - 统一走可读错误信封
        raise ToolError(f"{symbol} 分时读取失败：{exc}",
                        code="upstream", action="retry") from None
    data = raw if isinstance(raw, dict) else {}
    points = [p for p in (data.get("bars") or []) if isinstance(p, dict)]
    points.sort(key=lambda p: str(p.get("hm") or ""))
    day = str(data.get("trading_day") or "")[:10]
    is_index = target != "kline.query_min1_live"
    payload = {
        "bars": [_minute_row(p, is_index) for p in points],
        "count": len(points),
        "intraday": bool(points),
        "date": day,
        "updated_at": str(data.get("updated_at") or ""),
        "note": "" if points else _minute_empty_note(symbol, day),
    }
    return payload, day, []


def _minute_target(symbol: str) -> tuple[str, dict[str, Any]]:
    """分时入口按符号类别显式分流（2026-11-26 实测）。

    **指数键在个股分时入口下无数据**（返回空 MAP），裸码进指数入口返回
    ``None``——上游不自动改写路由，必须显式选入口：``index.`` 前缀走
    ``query_index_min1_live``（与个股分时**同形**：扁平 dict + bars
    ``{t, hm, close, ...}``，实测多 ``amount_delta/volume_delta`` 两个
    增量字段，归一时自然丢弃）；其余一律个股入口。
    """
    if symbol.startswith("index."):
        return "kline.query_index_min1_live", {"key": symbol}
    return "kline.query_min1_live", {"sym": symbol}


def _minute_row(point: dict[str, Any], is_index: bool) -> dict[str, Any]:
    """单点归一：``t`` + 现价 +（仅个股）当日均价 ``avg``。

    **均价是自算的**（2026-11-26 按「先查已有指标」确认上游分时字段无
    均价）：累计 ``amount / volume``（当日 VWAP；volume 已由 SDK 换算成
    股、amount 元）。**指数不算**——指数 volume 是成分股聚合量纲
    （units.py：不以手披露、不满足 ×close≈amount），除出来不是价格的
    量纲，画出来就是造假。比例离谱（>3× 或 <1/3× 现价，日 VWAP 与收盘
    价同在日内区间内，正常不可能到这量级）时丢弃——量纲破损的数据画出
    一条线比不画更骗人。
    """
    row: dict[str, Any] = {"t": point.get("t"), "price": point.get("close")}
    if is_index:
        return row
    amount = _f(point.get("amount"))
    volume = _f(point.get("volume"))
    close = _f(point.get("close"))
    if not (amount and volume and close):
        return row
    avg = amount / volume
    if not (close / 3 <= avg <= close * 3):
        return row
    row["avg"] = round(avg, 4)
    return row


def _f(value: Any) -> float | None:
    """数字归一（bool 不是数字）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _minute_empty_note(symbol: str, day: str) -> str:
    """空分时的原因。上游应答了（有 ``trading_day``）却没点数 = 未开盘
    或该标的无分钟源——ETF 上游不供分时，指数要用 ``index.`` 键。"""
    if symbol.startswith("index."):
        return f"{symbol} 无分时点数（该指数键上游无覆盖）"
    if day:
        return ("今日暂无分时点数（未开盘，或该标的无分钟源：ETF 上游"
                "不供分时；指数请用 index.hs300 这样的键）")
    return "上游无分时覆盖"
