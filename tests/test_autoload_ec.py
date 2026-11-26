"""``client/autoload`` 与 ``client/ec`` 的离线测试。

两条最关键的不变量在这里被钉死：

- **输入变了不静默重跑**（静默重跑在付费场景下等于偷钱）
- **预算闸/取消 → 零请求**（用「是否调用过 run」直接断言）
"""

from __future__ import annotations

import pytest
from workbench.client.autoload import (
    ALWAYS_REFRESH,
    DEFAULT_MAX_AGE_S,
    NEVER_REFRESH,
    CostClass,
    ViewState,
    decide,
    signature,
)
from workbench.client.ec import (
    BudgetExceeded,
    NeedsConfirm,
    attribute,
    check_budget,
    estimate,
    guard,
)
from workbench.core.envelope import EcEstimate

# ---------------------------------------------------------------- signature

def test_signature_is_key_order_insensitive() -> None:
    """键序不影响指纹——前端对象键序不稳定，否则同一请求会被判「输入变了」。"""
    assert signature({"a": 1, "b": 2}) == signature({"b": 2, "a": 1})


def test_signature_changes_with_values() -> None:
    assert signature({"a": 1}) != signature({"a": 2})


def test_signature_empty() -> None:
    assert signature(None) == ""
    assert signature({}) == ""


# ---------------------------------------------------------------- decide

def test_missing_result_runs() -> None:
    """没有结果 → 跑。"""
    d = decide(view=ViewState(), params={"x": 1}, now=1000.0)
    assert d.run is True
    assert d.state == "missing"


def test_manual_never_auto_runs() -> None:
    """``Manual`` 类（付费/重）绝不自动跑。"""
    d = decide(view=ViewState(), params={}, now=1000.0, cost=CostClass.MANUAL)
    assert d.run is False
    assert d.state == "manual"


def test_needs_setup_blocks_everything() -> None:
    """前置条件未满足 → 不跑（也不花钱）。"""
    v = ViewState(needs_setup=True, setup_hint="需要配置凭证")
    d = decide(view=v, params={}, now=1000.0)
    assert d.run is False
    assert d.state == "needs_setup"
    assert "凭证" in d.message


def test_max_age_zero_always_runs() -> None:
    """``max_age=0`` → 恒跑。"""
    v = ViewState(last_run_at=1000.0, last_signature=signature({"x": 1}))
    d = decide(view=v, params={"x": 1}, now=1000.0, max_age_s=ALWAYS_REFRESH)
    assert d.run is True


def test_max_age_negative_never_runs() -> None:
    """``max_age<0`` → 永不重跑。"""
    v = ViewState(last_run_at=0.0, last_signature=signature({"x": 1}))
    d = decide(view=v, params={"x": 1}, now=10**9, max_age_s=NEVER_REFRESH)
    assert d.run is False
    assert d.state == "fresh"


def test_max_age_boundary() -> None:
    """24h 边界：恰好未超龄不跑，超过才跑。"""
    v = ViewState(last_run_at=0.0, last_signature=signature({"x": 1}))
    fresh = decide(view=v, params={"x": 1}, now=DEFAULT_MAX_AGE_S,
                   max_age_s=DEFAULT_MAX_AGE_S)
    assert fresh.run is False
    stale = decide(view=v, params={"x": 1}, now=DEFAULT_MAX_AGE_S + 1,
                   max_age_s=DEFAULT_MAX_AGE_S)
    assert stale.run is True


def test_inputs_changed_does_not_rerun() -> None:
    """**输入变了不静默重跑**——这是「不偷钱」的核心。"""
    v = ViewState(last_run_at=1000.0, last_signature=signature({"x": 1}))
    d = decide(view=v, params={"x": 2}, now=1001.0)
    assert d.run is False
    assert d.state == "inputs_changed"
    assert d.inputs_changed is True
    assert "旧条件" in d.message


def test_one_attempt_per_visit() -> None:
    """本次访问已自动尝试过 → 不重复跑（防重渲染反复触发）。"""
    v = ViewState(last_run_at=1000.0, last_signature=signature({"x": 1}),
                  attempted_this_visit=True)
    d = decide(view=v, params={"x": 1}, now=1001.0, max_age_s=ALWAYS_REFRESH)
    assert d.run is False
    assert d.state == "throttled"


def test_force_bypasses_auto_gates_but_not_setup() -> None:
    """显式重跑绕过「一次尝试」与 ``Manual``，但**绕不过前置条件**。

    没凭证时强制重跑只会得到一个必然失败的请求，白费一次往返。
    """
    v = ViewState(attempted_this_visit=True)
    d = decide(view=v, params={}, now=1000.0, cost=CostClass.MANUAL, force=True)
    assert d.run is True

    blocked = decide(view=ViewState(needs_setup=True), params={}, now=1000.0,
                     force=True)
    assert blocked.run is False
    assert blocked.state == "needs_setup"


# ---------------------------------------------------------------- ec

class _FakeCli:
    """假 client：记录 ``cost_estimate`` 调用，用于断言「零请求」。"""

    def __init__(self, lo: int | None, hi: int | None) -> None:
        self.lo = lo
        self.hi = hi
        self.calls = 0

    def cost_estimate(self, target: str, **params) -> dict:
        self.calls += 1
        return {"ec_lo": self.lo, "ec_hi": self.hi, "model": "test"}


def test_estimate_returns_none_when_no_client() -> None:
    """无 client（演示模式）→ ``None`` 而非 0。0 会被读成「免费」。"""
    ec = estimate(None, "screener.query")
    assert ec.pred_lo is None
    assert ec.pred_hi is None
    assert ec.model == "none"


def test_budget_rejects_over_limit() -> None:
    """超上限 → 拒绝，并给出 fix_input。"""
    cli = _FakeCli(150_000, 250_000)
    v = check_budget(cli, "screener.query", {"where": "x"}, max_ec=200_000)
    assert v.allowed is False
    assert v.action == "fix_input"
    assert "250000" in v.message


def test_budget_allows_within_limit() -> None:
    cli = _FakeCli(70, 1000)
    v = check_budget(cli, "screener.query", max_ec=200_000)
    assert v.allowed is True


def test_budget_allows_when_no_model() -> None:
    """无成本模型不拦（拦了会让本来能用的接口不可用），但要如实告知。"""
    cli = _FakeCli(None, None)
    v = check_budget(cli, "some.unknown", max_ec=200_000)
    assert v.allowed is True
    assert v.ec.pred_hi is None


def test_guard_makes_zero_requests_when_over_budget() -> None:
    """**预算闸触发 → 零请求**（用「run 是否被调用」直接断言）。"""
    cli = _FakeCli(300_000, 400_000)
    called = []
    with pytest.raises(BudgetExceeded):
        guard(cli, "screener.query", lambda: called.append(1), max_ec=200_000)
    assert called == []


def test_guard_makes_zero_requests_when_not_confirmed() -> None:
    """**取消 → 零请求**。点了取消还在花钱比点确认才发现贵更摧毁信任。"""
    cli = _FakeCli(40_000, 60_000)
    called = []
    with pytest.raises(NeedsConfirm) as ei:
        guard(cli, "screener.query", lambda: called.append(1),
              max_ec=200_000, confirmed=False)
    assert called == []
    assert "取消不产生任何费用" in str(ei.value)


def test_guard_runs_when_confirmed() -> None:
    """确认后才执行。"""
    cli = _FakeCli(40_000, 60_000)
    called = []
    result, _ec = guard(cli, "screener.query", lambda: (called.append(1), "ok")[1],
                        max_ec=200_000, confirmed=True)
    assert called == [1]
    assert result == "ok"


def test_attribute_uses_response_metering() -> None:
    """归因用响应自带的 ``meta.metering``，不用共享 client 的 ``last_ec_cost``。"""
    ec = EcEstimate(pred_lo=70, pred_hi=1000, model="screener_light")
    out = attribute(ec, {"analysis.ec_cost": 219})
    assert out.actual == 219
    assert out.pred_lo == 70


def test_attribute_missing_metering_leaves_actual_none() -> None:
    """没有 metering → ``actual=None``，不伪造数字。"""
    ec = EcEstimate(pred_lo=70, pred_hi=1000, model="x")
    assert attribute(ec, None).actual is None
    assert attribute(ec, {}).actual is None
