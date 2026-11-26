"""``/api/backtest/run``：单标的回测。

**成本前置是这一页的硬要求**：不给 ``begin``/``end`` 的 ``backtest.run``
会取全历史（约 40 万 EC 量级）。所以本 handler 强制要求区间，并在
缺区间时返回一段可读的说明而不是直接扫全库。

**回测结果的定位是「历史事实的复现」，不是「策略建议」**：只展示成交
明细、净值曲线与八个汇总数字，不给「推荐参数」、不给「预期收益」
（``docs/PROJECT_SPEC`` §11 不替用户判断）。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import (
    ToolError,
    cost_of,
    err_from,
    fetch,
    int_param,
    normalize_bars,
    str_param,
)
from .summary import SUMMARY_LABELS, summary

__all__ = ["handle", "TARGET", "RULES", "SUMMARY_LABELS"]

TARGET = "backtest.run"

#: 组合门面：``backtest.run`` 不在目录里，必须走 ``cli.backtest.run()``。
FACADE: tuple[str, str] = ("backtest", "run")

#: 支持的规则（``ma_cross`` 用均线，其余用估值阈值）。
RULES: tuple[str, ...] = ("ma_cross", "pe", "pb", "ps", "pr")


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    try:
        symbol = _symbol(params)
        rule = _rule(params)
        begin = str_param(params, "begin")
        end = str_param(params, "end")
        if not (begin and end):
            raise ToolError(
                "回测必须指定区间（begin/end）：不给区间会取全历史，"
                "单次可达数十万 EC。请先用「近两年」之类的区间试。",
                code="need_range",
                action="fix_input",
            )
        call_params = _call_params(params, symbol, rule, begin, end)
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    try:
        raw, as_of = fetch(ctx, TARGET, call_params, facade=("backtest", "run"))
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    payload = raw if isinstance(raw, dict) else {}
    trades = _trades(payload.get("trades"))
    equity = _equity(payload.get("equity"))
    bars, bars_warnings = _price_bars(ctx, symbol, begin, end)
    warnings = list(payload.get("warnings") or []) + bars_warnings
    # 信封 as_of = **数据的实际末日**（净值/价格两路取最大），不是请求的
    # end 参数——end 是「声称的区间」，上游可能没有数据到那天；数据事实优先
    as_of = _data_as_of(equity, bars) or as_of or end
    return ok_envelope(
        {
            "symbol": symbol,
            "rule": rule,
            "begin": begin,
            "end": end,
            "params": call_params,
            "trades": trades,
            "marks": _marks(trades),
            "bars": bars,
            "equity": equity,
            "summary": summary(payload.get("summary"), equity, trades),
            "summary_labels": [
                {"key": k, "label": lbl, "format": fmt} for k, lbl, fmt in SUMMARY_LABELS
            ],
            "caliber": payload.get("caliber") or {},
            "warnings": warnings,
        },
        as_of=as_of,
        meta={
            "note": "回测为历史复现，不构成策略建议；成交口径见 caliber；"
            "价格 K 线是另一次 kline.bars 区间取数（独立计费，"
            "失败时降级为仅净值曲线，见 warnings）"
        },
        freshness="fresh",
        ec=_ec(ctx, call_params),
        warnings=warnings,
    )


def _symbol(params: dict[str, Any]) -> str:
    sym = str_param(params, "symbol")
    if not sym:
        raise ToolError("缺少标的代码（symbol）", code="missing_param")
    return sym


def _rule(params: dict[str, Any]) -> str:
    rule = str_param(params, "rule") or "ma_cross"
    rule = "ma_cross" if rule == "ma" else rule
    if rule not in RULES:
        raise ToolError(f"rule 只支持 {'/'.join(RULES)}，收到 {rule!r}", code="param")
    return rule


def _call_params(
    params: dict[str, Any], symbol: str, rule: str, begin: str, end: str
) -> dict[str, Any]:
    """组装底层调用参数。估值规则必须带 ``buy``/``sell`` 阈值。"""
    out: dict[str, Any] = {
        "symbol": symbol,
        "rule": rule,
        "begin": begin,
        "end": end,
        "cash": float(int_param(params, "cash", 1_000_000, lo=10_000, hi=10**9)),
    }
    if rule == "ma_cross":
        out["fast"] = int_param(params, "fast", 5, lo=1, hi=250)
        out["slow"] = int_param(params, "slow", 20, lo=2, hi=500)
        if out["fast"] >= out["slow"]:
            raise ToolError(
                f"快线周期必须小于慢线（收到 {out['fast']} ≥ {out['slow']}）", code="param"
            )
        return out
    buy = params.get("buy")
    sell = params.get("sell")
    if buy is None or sell is None:
        raise ToolError(f"rule={rule} 需要 buy/sell 阈值", code="missing_param")
    try:
        out["buy"], out["sell"] = float(buy), float(sell)
    except (TypeError, ValueError):
        raise ToolError("buy/sell 必须是数字", code="param") from None
    if not 0 < out["buy"] < out["sell"]:
        raise ToolError(
            f"估值阈值需 0 < buy < sell（收到 {out['buy']}/{out['sell']}）", code="param"
        )
    return out


def _trades(raw: Any) -> list[dict[str, Any]]:
    """成交明细。字段按侧别不同：卖出才有 ``pnl``/``ret``/``hold_days``。"""
    if not isinstance(raw, list):
        return []
    keys = ("date", "side", "price", "shares", "amount", "fee", "reason", "pnl", "ret", "hold_days")
    return [{k: row.get(k) for k in keys if k in row} for row in raw if isinstance(row, dict)]


def _marks(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """买卖点标记（标到价格 K 线上）。

    ``side`` **原样透传**：只认 ``buy``/``sell`` 是渲染层的口径，未知值
    在前端画成中性标记并计数——不能在 handler 静默丢掉，那会把「上游换了
    枚举」变成「买卖点莫名少了几个」。日期/价格缺失的行标不出来，如实
    留在 ``trades`` 里（表格始终完整显示全部成交）。
    """
    out: list[dict[str, Any]] = []
    for t in trades:
        date = t.get("date")
        price = t.get("price")
        if not date or not isinstance(price, (int, float)) or isinstance(price, bool):
            continue
        out.append({"date": date, "price": price, "side": str(t.get("side") or "")})
    return out


def _price_bars(
    ctx: Any, symbol: str, begin: str, end: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """回测区间内的日 K（买卖点要标在**价格**上，不是净值上）。

    ``backtest.run`` 只返回净值——净值受现金与费用影响，标在它上面会让
    人把折线当成价格走势。故额外取一次 ``cli.kline.bars``（成本独立于
    回测，信封 meta 如实披露）。**取不到不终止**：只降级掉「标在价格
    上」这一能力，给 warning 而不是整页报错。
    """
    try:
        raw, _ = fetch(
            ctx,
            "kline.bars",
            {"symbol": symbol, "begin": begin, "end": end},
            facade=("kline", "bars"),
        )
    except Exception as exc:  # noqa: BLE001 - K 线失败只降级，不毁掉回测
        return [], [f"价格 K 线未取到（{exc}），买卖点无法标在价格图上"]
    bars, skipped = normalize_bars(raw)
    warnings: list[str] = []
    if not bars:
        warnings.append("回测区间内没有日 K，买卖点无法标在价格图上")
    elif skipped:
        warnings.append(f"{skipped} 行 K 线缺少开高低收，未绘制")
    return bars, warnings


def _equity(raw: Any) -> list[dict[str, Any]]:
    """净值曲线（``[{date, nav}]``）。"""
    if not isinstance(raw, list):
        return []
    return [{"date": r.get("date"), "nav": r.get("nav")} for r in raw if isinstance(r, dict)]


def _data_as_of(equity: list[dict[str, Any]], bars: list[dict[str, Any]]) -> str:
    """两路取数的**实际末日**（净值与价格来自两次独立上游，取最大）。

    「截至」必须是数据事实：请求参数 ``end`` 只是用户声称的区间终点，
    上游可能根本没有数据到那天。行内日期缺失的行不参与比较。
    """
    dates = [str(e.get("date") or "")[:10] for e in equity] + [
        str(b.get("date") or "")[:10] for b in bars
    ]
    dates = [d for d in dates if d]
    return max(dates) if dates else ""


def _ec(ctx: Any, call_params: dict[str, Any]) -> EcEstimate:
    """成本预估 —— 统一走 ``_shared.cost_of``（唯一实现）。

    回测的成本 ≈ ``kline.bars`` 的行数 × 单价，由 SDK 的成本模型回答。
    """
    return cost_of(getattr(ctx, "fetcher", None), TARGET, call_params)
