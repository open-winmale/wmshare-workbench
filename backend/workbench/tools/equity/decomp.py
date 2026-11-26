"""个股研究 —— 持有收益拆解分区（``income.decomp_one``）。

**这是全站最贵的分区**，实测（2026-11-25，免注册池）：

| 情形 | 实测 EC |
|---|---|
| 热态 5 年 | 15,814 |
| 热态 10 年 | 328,857 |
| 冷态首查 10 年（AT 锚点物化惩罚） | 721,953 |

因此它恒在 ``EXPENSIVE_SECTIONS`` 里，必须显式确认才发请求。**成本随年限
超线性增长**（5 年 → 10 年涨 20 倍），所以默认年限取 5 而不是 10：
默认给最贵的那个档位等于每次都替用户做了一次昂贵选择。

**口径（重要）**：股息贡献 = 后复权 − 不复权的差值，**含再投效应**，
不是「分红金额 ÷ 买入价」。所以 ``price_return + dividend_return ==
total_return`` 恒成立，但 ``dividend_return`` 不等于同期股息率之和。
页面上不能把它标成「股息率」。

**``ok=false`` 是有效响应**：次新股 K 线覆盖不足时上游返回
``{ok: false, reason: "K 线覆盖不足（次新股或无数据）"}``，**没有**任何
收益字段。这是「这只票算不出来」，不是「请求失败」——必须如实显示原因，
而不是抛成错误让用户以为接口坏了。
"""

from __future__ import annotations

from typing import Any

from ...tools._shared import ToolError, cost_of, fetch, int_param

__all__ = ["build", "ALLOWED_YEARS", "DEFAULT_YEARS", "estimate", "years_of"]

#: 上游只接受这三档（``income.decomp_one`` 的 ``years``）。
ALLOWED_YEARS: tuple[int, ...] = (3, 5, 10)

#: 默认年限。**取 5 不取 10**：10 年档实测可达 72 万 EC，默认值不该是最贵的。
DEFAULT_YEARS = 5

#: 归因块的中文名（``attribution`` 的键 → 展示名）。
ATTRIBUTION_LABELS: tuple[tuple[str, str, str], ...] = (
    ("pe_start", "期初 PE", "num"),
    ("pe_end", "期末 PE", "num"),
    ("eps_start", "期初 EPS", "num"),
    ("eps_end", "期末 EPS", "num"),
    ("g_pe", "PE 变化贡献", "pct"),
    ("g_eps", "EPS 变化贡献", "pct"),
)

#: 汇总卡片（口径由后端声明，前端不猜）。
SUMMARY_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("total_return", "总收益", "pct"),
    ("price_return", "价格贡献", "pct"),
    ("dividend_return", "股息贡献", "pct"),
    ("cagr_total", "年化总收益", "pct"),
    ("cagr_price", "年化价格", "pct"),
    ("cagr_dividend", "年化股息", "pct"),
    ("close_start", "期初价", "num"),
    ("close_end", "期末价", "num"),
)


def build(ctx: Any, symbol: str,
          params: dict[str, Any]) -> tuple[Any, str, list[str]]:
    """持有收益拆解（高成本，调用前必须已确认）。"""
    years = _years(params)
    raw, as_of = fetch(ctx, "income.decomp_one",
                       {"sym": symbol, "years": years})
    if not isinstance(raw, dict) or not raw:
        raise ToolError(f"{symbol} 无收益拆解数据", code="upstream",
                        action="retry")

    if not raw.get("ok"):
        # 有效响应但算不出来：如实给出原因，不当成错误
        reason = str(raw.get("reason") or "K 线覆盖不足")
        return ({"ok": False, "reason": reason, "years": years,
                 "symbol": symbol}, as_of,
                [f"{symbol} 无法拆解：{reason}"])

    warnings = _warnings(raw)
    # 信封 as_of 用块内的 **end_date**（拆解区间的真实末日）：上游信封
    # as_of 恒空，此前把块内已有的日期浪费掉了，真实模式页顶永远没有「截至」
    end_date = str(raw.get("end_date") or "")[:10]
    return ({"ok": True,
             "years": years,
             "symbol": symbol,
             "span_years": raw.get("span_years"),
             "start_date": raw.get("start_date"),
             "end_date": raw.get("end_date"),
             "summary": _summary(raw),
             "attribution": _attribution(raw),
             "yearly": _yearly(raw.get("yearly")),
             "monthly": _monthly(raw.get("monthly"))},
            end_date or as_of, warnings)


def _years(params: dict[str, Any]) -> int:
    """年限钳到上游接受的三档，就近取。

    参数校验先过 ``int_param``（非整数要报可读错误），再钳档位。
    """
    int_param(params, "years", DEFAULT_YEARS, lo=1, hi=50)
    return years_of(params)


def _summary(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """汇总卡片：值 + 后端声明的口径。

    ``dividend_return`` 的标签是「股息贡献」而不是「股息率」——它是
    后复权与不复权的差值（含再投），不是分红 ÷ 买入价。
    """
    return [{"key": k, "label": label, "value": raw.get(k), "format": fmt}
            for k, label, fmt in SUMMARY_FIELDS if k in raw]


def _attribution(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """EPS × PE 归因（Dupont 式的两因子分解）。缺失时返回空列表。"""
    block = raw.get("attribution")
    if not isinstance(block, dict) or not block:
        return []
    return [{"key": k, "label": label, "value": block.get(k), "format": fmt}
            for k, label, fmt in ATTRIBUTION_LABELS if k in block]


def _yearly(raw: Any) -> list[dict[str, Any]]:
    """逐年表：``year / price_pct / div_pct / total_pct``。"""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        out.append({"year": str(row.get("year") or ""),
                    "price_pct": row.get("price_pct"),
                    "div_pct": row.get("div_pct"),
                    "total_pct": row.get("total_pct")})
    out.sort(key=lambda r: r["year"])
    return out


def _monthly(raw: Any) -> list[dict[str, Any]]:
    """月末累计序列：``date / cum_price / cum_total / close_nr``。

    只保留三条曲线需要的字段——``close_hfq`` 与 ``yield_ttm`` 也在真实
    返回里，但前端画累计曲线用不上；留着会让响应体白白变大。
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        out.append({"date": str(row.get("date") or ""),
                    "cum_price": row.get("cum_price"),
                    "cum_total": row.get("cum_total"),
                    "close_nr": row.get("close_nr")})
    out.sort(key=lambda r: r["date"])
    return out


def _warnings(raw: dict[str, Any]) -> list[str]:
    """如实标注「收益差为 0」这种可疑但可能是真的情况。"""
    warnings: list[str] = []
    div = raw.get("dividend_return")
    if isinstance(div, (int, float)) and div == 0:
        warnings.append(
            "股息贡献为 0：该区间内未检测到除权除息（次新股或不分红），"
            "不是数据缺失")
    span = raw.get("span_years")
    if isinstance(span, (int, float)) and span < 1:
        warnings.append(f"实际覆盖仅 {span:.1f} 年，样本过短，"
                        f"年化指标参考价值有限")
    return warnings


# --------------------------------------------------------------------------
# 确认前的成本预估
# --------------------------------------------------------------------------

def years_of(params: dict[str, Any]) -> int:
    """本次请求真正会用的年限。**确认框与执行必须用同一个值**。"""
    raw = params.get("years", DEFAULT_YEARS)
    try:
        want = int(raw)
    except (TypeError, ValueError):
        want = DEFAULT_YEARS
    if want in ALLOWED_YEARS:
        return want
    return min(ALLOWED_YEARS, key=lambda y: abs(y - want))


def estimate(ctx: Any, symbol: str, params: dict[str, Any]) -> dict[str, Any]:
    """本分区的成本预估（零请求）。

    有模型时给区间，**无模型时 ``known=False`` 且 ``lo/hi`` 为 ``None``**
    —— 绝不能写 0（0 会被读成免费）。

    **模型上界可能偏低**：SDK 侧 ``measured`` 档的 ``ec_hi=200_000``，而实测
    单票尖刺达 721,953 EC（`DEBT.md` D-32 有原始数据）。模型不在本仓，
    改不了；因此额外给出 ``measured_peak`` 让确认框能如实标注「实测可到多少」。
    """
    ec = cost_of(getattr(ctx, "fetcher", None), "income.decomp_one",
                 {"sym": symbol, "years": years_of(params)})
    return {"known": ec.known, "lo": ec.pred_lo, "hi": ec.pred_hi,
            "model": ec.model, "measured_peak": MEASURED_PEAK}


#: 实测单票尖刺（2026-11-25）。**不是模型值**，是真实观测到的最高一笔；
#: 用于在模型上界之下补一句「实际可能更贵」，避免用户按 20 万预留而被吓到。
MEASURED_PEAK = 721_953


def cost_message(estimate_block: dict[str, Any], title: str) -> str:
    """确认提示文案：有模型给区间，无模型说「未知」。

    ``hi`` 低于 ``measured_peak`` 时**必须补一句实测峰值** —— 只在确认框里写
    20 万、实际扣了 72 万，是「成本可见」原则的破口。
    """
    if not estimate_block.get("known"):
        return (f"{title} 属于高成本分区；该请求没有成本模型可预估。"
                f"实测单票尖刺可达 "
                f"{estimate_block.get('measured_peak', 0):,} EC。"
                f"确认后才会发起请求（当前零请求）。")
    lo, hi = estimate_block.get("lo"), estimate_block.get("hi")
    peak = int(estimate_block.get("measured_peak") or 0)
    tail = ""
    if peak > int(hi or 0):
        tail = (f"注意：模型上界低于实测尖刺——单票最坏观测到 "
                f"{peak:,} EC，请按此留余量。")
    return (f"{title} 属于高成本分区，本次预估 {lo:,}–{hi:,} EC"
            f"（模型 {estimate_block.get('model')}）；换标的或换年限会变。"
            f"{tail}确认后才会发起请求（当前零请求）。")
