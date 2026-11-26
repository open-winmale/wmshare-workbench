"""形状夹具（测试专用） —— 业绩披露与收益拆解（形状与真实返回同构）。

拆出独立文件的理由：这两块是``equity`` 分区里结构最复杂的（预告三块嵌套 +
拆解六块），塞进 ``shape_gen`` 会让它一路涨过单文件上限。文件名
``shape_extra`` 表示它只产出这两类数据，收窄逻辑仍在 ``shape_data``。

**形状纪律同 ``shape_gen``**：字段名、单位、嵌套层级逐一对齐真实响应。
任何偏差都会让页面「演示态跑通、真机白屏」。
"""

from __future__ import annotations

from typing import Any

from shape_gen import ANCHOR_DATE, SHAPE_AS_OF

__all__ = ["forecast_snapshot", "decomp_one"]


def forecast_snapshot(symbol: str, name: str = "") -> dict[str, Any]:
    """业绩披露快照 —— 与真实 ``forecast.snapshot`` 同构（``yjyg``/``yjkb``/
    ``next_disclosure`` 三块）。

    **保留上游的 ``0`` 语义**：真实的 ``deduct_lower``/``deduct_upper``
    在多数票上是 ``0``（上游没给扣非区间）。形状夹具（测试专用）也照给 0，让
    「0 要归成 None」这条处理在演示态下真的被执行到——如果这里给一个
    漂亮的非零值，那段归一逻辑在演示态永远不会被触发。
    """
    return {
        "symbol": symbol,
        # 真实返回带数据截至日；年龄计算相对它（不相对 wall clock）
        "as_of": SHAPE_AS_OF,
        "yjyg": {
            "report_date": "2025-12-31",
            "ann_date": "2026-01-23",
            "first_ann_date": "2026-01-23",
            "predict_type": "略增",
            "np_lower": 6.92e10,
            "np_upper": 7.18e10,
            "np_amp_lower": 0.112,
            "np_amp_upper": 0.154,
            "np_preyear": 6.22e10,
            "rev_lower": 1.868e11,
            "rev_upper": 1.912e11,
            "rev_amp_lower": 0.078,
            "rev_amp_upper": 0.103,
            # 扣非区间上游常给 0 —— 演示照给，让归一逻辑被真的执行
            "deduct_lower": 0,
            "deduct_upper": 0,
            "revised_count": 1,
            "content": ("预计2025年1-12月归属于上市公司股东的净利润盈利约:"
                        "70,500,000万元,同比上年增长:13.3%左右。"),
            "source": "",
        },
        "yjkb": {
            "report_date": "2026-09-30",
            "ann_date": "2026-10-18",
            "revenue": 1.436e11,
            "netprofit": 5.28e10,
            "np_yoy": 0.0891,
            "rev_yoy": 0.0642,
            "roe": 0.2417,
            "basic_eps": 42.06,
            "bvps": 174.02,
            "netprofit_ly": 4.848e10,
            "revenue_ly": 1.349e11,
            "source": "",
        },
        # 真实返回里这块多数是 null（未预约）——演示给一个值，让「有预约」
        # 这条渲染路径也被覆盖；缺少 null 的分支由单测另测。
        "next_disclosure": {"report_date": "2027-03-28"},
    }


def decomp_one(symbol: str, years: int = 5) -> dict[str, Any]:
    """收益拆解 —— 与真实 ``income.decomp_one`` 同构。

    校验口径：``price_return + dividend_return == total_return``（恒等式）。
    形状夹具（测试专用）也满足它——否则演示态跑出来的拆解自己就不平，用户会先怀疑
    我们的加法。
    """
    span = float(years) - 0.08
    start_year = ANCHOR_DATE.year - years
    monthly = _monthly_curve(start_year, years)
    price_return = 0.1836
    dividend_return = 0.0964
    return {
        "schema": "income-decomp/v1",
        "code": symbol,
        "years": years,
        "ok": True,
        "start_date": monthly[0]["date"],
        "end_date": monthly[-1]["date"],
        "span_years": span,
        "close_start": 1286.40,
        "close_end": 1522.80,
        "total_return": round(price_return + dividend_return, 10),
        "price_return": price_return,
        "dividend_return": dividend_return,
        "cagr_total": 0.0521,
        "cagr_price": 0.0343,
        "cagr_dividend": 0.0177,
        "attribution": {
            "pe_start": 20.14,
            "pe_end": 19.62,
            "eps_start": 63.88,
            "eps_end": 77.61,
            "g_pe": -0.0258,
            "g_eps": 0.2148,
        },
        "yearly": _yearly_rows(start_year, years),
        "monthly": monthly,
    }


def _monthly_curve(start_year: int, years: int) -> list[dict[str, Any]]:
    """月末累计序列（升序）。末值为该年限下的真实终值。"""
    n = years * 12
    return [{"date": f"{start_year + i // 12}-{(i % 12) + 1:02d}-28",
             "close_nr": round(1286.40 * (1 + i * 0.0031), 2),
             "close_hfq": round(1286.40 * (1 + i * 0.0044), 4),
             "cum_price": round(i * 0.0031, 10),
             "cum_total": round(i * 0.0047, 10),
             "yield_ttm": 0.0353}
            for i in range(n)]


def _yearly_rows(start_year: int, years: int) -> list[dict[str, Any]]:
    """逐年表（升序）。``总 = 价格 + 股息`` 逐行成立。"""
    out: list[dict[str, Any]] = []
    for i in range(years):
        price = round(-0.086 + i * 0.054, 6)
        div = round(0.0172 + i * 0.0018, 6)
        out.append({"year": str(start_year + i),
                    "price_pct": price,
                    "div_pct": div,
                    "total_pct": round(price + div, 10)})
    return out


#: 演示里「次新股算不出来」的那只票（对应真实的 ``ok=false`` 降级形状）。
#: 必须演示它，否则前端那条分支永远没被渲染过。
DECOMP_INSUFFICIENT: frozenset[str] = frozenset({"300750"})


def decomp_insufficient(symbol: str, years: int) -> dict[str, Any]:
    """``ok=false`` 的真实形状：只有 ``code/ok/reason/schema/years``。"""
    return {"code": symbol, "ok": False, "years": years,
            "schema": "income-decomp/v1",
            "reason": "K 线覆盖不足（次新股或无数据）"}


def quote_date() -> str:
    """数据截至日（从锚点推导，不手写）。"""
    return SHAPE_AS_OF


# --------------------------------------------------------------------------
# 按参数收窄（供 ``shape_data._RESHAPERS`` 直接登记）
# --------------------------------------------------------------------------

def shape_forecast(params: dict[str, Any]) -> dict[str, Any]:
    """业绩披露快照（按标的收窄）。

    不仅按标的变：**标的只影响 ``symbol`` 字段**，三块内容照给——真实的
    上游对未收录代码也是返回同形结构（不是空对象），演示要一致。
    """
    sym = str(params.get("sym") or params.get("symbol") or "") or "600519"
    return forecast_snapshot(sym)


def shape_decomp(params: dict[str, Any]) -> dict[str, Any]:
    """收益拆解（按标的 + 年限）。次新股走 ``ok=false`` 降级形状。"""
    sym = str(params.get("sym") or params.get("symbol") or "") or "600519"
    try:
        years = int(params.get("years") or 5)
    except (TypeError, ValueError):
        years = 5
    if sym in DECOMP_INSUFFICIENT:
        return decomp_insufficient(sym, years)
    return decomp_one(sym, years)


def shape_forecast_latest(params: dict[str, Any]) -> Any:
    """``forecast.yjyg_latest`` 只返回预告那一块（不是整个快照）。"""
    return shape_forecast(params).get("yjyg")
