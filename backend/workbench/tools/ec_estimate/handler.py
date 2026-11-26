"""``/api/ec/estimate``：EC 试算（**零请求**）。

这是「花钱之前先算账」这条原则的独立入口：用户可以在真正跑任何工具前，
先问「这个操作要花多少」。

**无模型时 ``pred_*`` 必须是 ``None``**，不能写 0。0 会被读成「免费」，
而这个错误会让用户在最贵的操作上毫无防备。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import ToolError, cost_of, err_from, str_param

__all__ = ["handle", "ESTIMABLE", "DEFAULT_MAX_EC"]

#: 可试算的 target（白名单，避免用户把任意函数名拼进来）。
ESTIMABLE: tuple[str, ...] = (
    "screener.query",
    "backtest.run",
    "valuation.daily_basic",
    "rptdom.statement",
    "pdf_doc.read_markdown",
    "dividend.decomp",
    "moneyflow.universe",
)

#: 单次请求的 EC 上限（与 ``client/ec`` 一致）。
DEFAULT_MAX_EC = 200_000


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    try:
        target = str_param(params, "target")
        if not target:
            raise ToolError("缺少目标接口（target）", code="missing_param")
        if target not in ESTIMABLE:
            raise ToolError(
                f"{target} 不在可试算白名单；可选 "
                f"{'/'.join(ESTIMABLE)}", code="param")
        call_params = params.get("params") or {}
        if not isinstance(call_params, dict):
            raise ToolError("params 必须是对象", code="param")
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    ec = cost_of(getattr(ctx, "fetcher", None), target, call_params)
    over = (ec.pred_hi or 0) > DEFAULT_MAX_EC
    return ok_envelope(
        {
            "target": target,
            "params": call_params,
            "estimate": ec.as_dict(),
            "max_ec": DEFAULT_MAX_EC,
            "over_budget": over,
            "estimable": list(ESTIMABLE),
            "message": _message(ec, over),
        },
        as_of="",
        meta={"note": "试算不发起任何上游请求", "zero_requests": True},
        freshness="fresh",
        ec=EcEstimate(model="local"))


def _message(ec: EcEstimate, over: bool) -> str:
    if not ec.known:
        return "该接口没有成本模型，无法预估——这里显示「未知」而不是 0（0 会被误读成免费）。请求仍会按实际用量计费。"
    if over:
        return (f"预估最高 {ec.pred_hi:,} EC，超过单次上限 "
                f"{DEFAULT_MAX_EC:,}；工具会要求二次确认。")
    return (f"预估 {ec.pred_lo:,}–{ec.pred_hi:,} EC"
            f"（模型 {ec.model}）。")
