"""EC 预算闸：花钱之前先算账，超了就**一个请求都不发**。

**为什么这层必须独立**：成本纪律写在文档里不会生效，必须写在代码路径上。
两条硬规则：

1. **预算闸触发 → 零请求**。不是「先发再检查」，是压根不发。
2. **取消 → 零请求**。用户点了取消还在花钱，比点了确认才发现很贵更摧毁信任。

成本数字来自 ``wmshare.client.estimate_cost``（平台实测模型），本模块只做
闸门与归因，**不自己估算**——否则会出现两套不一致的数字。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...core.envelope import EcEstimate

__all__ = [
    "DEFAULT_MAX_EC",
    "BudgetExceeded",
    "BudgetVerdict",
    "NeedsConfirm",
    "attribute",
    "check_budget",
    "estimate",
    "guard",
]

#: 单次聚合请求的 EC 上限。与 MCP 层同量级（200,000）。
DEFAULT_MAX_EC = 200_000


@dataclass(frozen=True)
class BudgetVerdict:
    """预算判决。``allowed=False`` 时调用方**不得发出任何请求**。"""

    allowed: bool
    ec: EcEstimate
    #: 拒绝原因（面向用户）
    message: str = ""
    #: 建议动作，与信封的 ``action`` 对齐
    action: str = ""

    @property
    def requires_confirm(self) -> bool:
        """是否属于「付费/重」——需要二次确认。"""
        return self.allowed and (self.ec.pred_hi or 0) > 0


def estimate(
    cli: Any,
    target: str,
    params: dict[str, Any] | None = None,
) -> EcEstimate:
    """调 ``cli.cost_estimate`` 得到区间。

    ``cli`` 为 ``None``（演示模式/未安装 wmshare）时返回「无模型」——
    **不是 0**。0 会被读成「免费」。
    """
    if cli is None:
        return EcEstimate(model="none")
    try:
        raw = cli.cost_estimate(target, **(params or {}))
    except Exception:  # noqa: BLE001 - 估算失败不该阻断主流程
        return EcEstimate(model="unavailable")
    lo = raw.get("ec_lo")
    hi = raw.get("ec_hi")
    return EcEstimate(
        pred_lo=int(lo) if isinstance(lo, (int, float)) else None,
        pred_hi=int(hi) if isinstance(hi, (int, float)) else None,
        actual=None,
        model=str(raw.get("model") or "none"),
    )


def check_budget(
    cli: Any,
    target: str,
    params: dict[str, Any] | None = None,
    *,
    max_ec: int = DEFAULT_MAX_EC,
) -> BudgetVerdict:
    """预估并在超限时拒绝。

    超限时 ``allowed=False`` 且 ``action="fix_input"``——调用方据此**直接返回
    错误信封，不发请求**。这条由测试强制（断言请求计数为 0）。
    """
    ec = estimate(cli, target, params)
    hi = ec.pred_hi
    if hi is None:
        # 无成本模型：不拦（拦了会让本来能用的接口不可用），但要如实告知
        return BudgetVerdict(allowed=True, ec=ec)
    if hi > max_ec:
        return BudgetVerdict(
            allowed=False, ec=ec,
            message=(f"本次预估 {ec.pred_lo or 0}–{hi} EC，"
                     f"超过单次上限 {max_ec}；请拆小范围或分批查询"),
            action="fix_input",
        )
    return BudgetVerdict(allowed=True, ec=ec)


def attribute(
    ec: EcEstimate,
    metering: dict[str, Any] | None,
) -> EcEstimate:
    """把实际消耗填进 ``ec``——**用响应自带的 ``meta.metering``**。

    绝不用共享 client 的 ``last_ec_cost``：那是实例级无锁字段，
    并发请求下会串账（把 A 请求的消耗记到 B 头上）。
    """
    actual = None
    if isinstance(metering, dict):
        raw = metering.get("analysis.ec_cost")
        if isinstance(raw, (int, float)):
            actual = int(raw)
    return EcEstimate(pred_lo=ec.pred_lo, pred_hi=ec.pred_hi,
                      actual=actual, model=ec.model)


def guard(
    cli: Any,
    target: str,
    run: Callable[[], Any],
    params: dict[str, Any] | None = None,
    *,
    max_ec: int = DEFAULT_MAX_EC,
    confirmed: bool = False,
) -> tuple[Any, EcEstimate]:
    """组合闸门：算 → 判 → （未确认则中止）→ 执行 → 归因。

    ``confirmed=False`` 且需要确认时抛 ``NeedsConfirm``，**不执行 ``run``**。
    这是「取消后零请求」的实现位置。
    """
    verdict = check_budget(cli, target, params, max_ec=max_ec)
    if not verdict.allowed:
        raise BudgetExceeded(verdict)
    if verdict.requires_confirm and not confirmed:
        raise NeedsConfirm(verdict)
    result = run()
    return result, verdict.ec


class BudgetExceeded(RuntimeError):
    """预估超单次上限——请求未发出。"""

    def __init__(self, verdict: BudgetVerdict) -> None:
        super().__init__(verdict.message)
        self.verdict = verdict


class NeedsConfirm(RuntimeError):
    """需要用户二次确认——请求未发出。"""

    def __init__(self, verdict: BudgetVerdict) -> None:
        super().__init__(
            f"该操作预估 {verdict.ec.pred_lo or 0}–{verdict.ec.pred_hi or 0} EC，"
            f"确认后执行；取消不产生任何费用")
        self.verdict = verdict
