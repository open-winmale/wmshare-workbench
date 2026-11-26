"""成本感知加载：什么时候可以自动跑，什么时候必须问人。

移植对标物的 ``AutoLoadPolicy``，把它的「AI 信用点」模型精确映射到 EC：

| 类别 | 触发 | 例子 |
|---|---|---|
| ``AutoRun`` | 打开即跑，``max_age`` 内不重跑 | ``info.profile``、缓存命中的 ``index.trend`` |
| ``Manual`` | 显式点击 + 二次确认（显示 EC 区间） | 重列 ``screener.query``、``dividend.decomp`` |
| ``NeedsSetup`` | 先提示配置 | 无凭证、缺必填参数 |

**三条不变量**（逐条对齐原版，因为它们是「不烧钱」的全部依据）：

1. **每次访问最多一次自动尝试**——不因重渲染反复触发。
2. **输入变了不静默重跑**——显示「结果来自旧条件」，用户显式点重跑。
   静默重跑在付费场景下是最恶劣的行为：用户以为自己只是切了个筛选条件，
   实际上每次输入都花了一次钱。
3. **用户付过费的（Manual）结果永不丢弃**——由 ``hub`` 的 ``expensive`` 保证。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "ALWAYS_REFRESH",
    "NEVER_REFRESH",
    "DEFAULT_MAX_AGE_S",
    "CostClass",
    "LoadDecision",
    "signature",
    "decide",
]


class CostClass(Enum):
    """视图的成本类别——决定它能不能自动跑。"""

    AUTO = "auto"        # 免费/本地/缓存命中，可自动
    MANUAL = "manual"    # 付费/重，必须显式触发
    SETUP = "setup"      # 先满足前置条件


#: ``max_age=0`` → 每次都重跑。
ALWAYS_REFRESH = 0
#: ``max_age<0`` → 永远不重跑（只用手上的）。
NEVER_REFRESH = -1
#: 默认一天——与对标物 ``kDefaultMaxAgeSeconds = 24 * 3600`` 一致。
DEFAULT_MAX_AGE_S = 24 * 3600


@dataclass(frozen=True)
class LoadDecision:
    """一次「要不要跑」的决定。"""

    run: bool
    #: ``fresh`` / ``stale`` / ``missing`` / ``inputs_changed`` /
    #: ``manual`` / ``needs_setup`` / ``throttled``
    state: str
    #: 面向用户的说明；``run=True`` 且有结果时为空
    message: str = ""
    #: 是否需要用「结果来自旧条件」提示
    inputs_changed: bool = False


def signature(params: dict[str, Any] | None) -> str:
    """参数的规范化指纹（SHA-1 前 16 hex）。

    **键序不敏感**是必须的：前端对象的键顺序不稳定，若顺序影响指纹，
    同一个请求会被判成「输入变了」而反复重跑——正是要避免的烧钱行为。
    """
    if not params:
        return ""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, default=str)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class ViewState:
    """一个视图的记忆状态（调用方持有，通常是 SQLite 或内存）。"""

    #: 上次跑成功时的时间戳（``now()`` 基准）
    last_run_at: float | None = None
    #: 上次跑成功时的参数指纹
    last_signature: str = ""
    #: 本次访问是否已经自动尝试过（保证「最多一次」）
    attempted_this_visit: bool = False
    #: 是否需要前置条件
    needs_setup: bool = False
    #: 前置条件未满足的说明
    setup_hint: str = ""


def _gate_setup(view: ViewState, force: bool) -> LoadDecision | None:
    """前置条件与「最多一次」门。``force`` 也绕不过前置条件。"""
    if view.needs_setup:
        return LoadDecision(run=False, state="needs_setup",
                            message=view.setup_hint or "需要先完成配置")
    if force:
        return LoadDecision(run=True, state="forced")
    if view.attempted_this_visit:
        return LoadDecision(
            run=False, state="throttled",
            message="本次访问已尝试获取过，如需重试请手动刷新")
    return None


def _gate_inputs(view: ViewState, params: dict[str, Any] | None) -> LoadDecision | None:
    """输入指纹门。变了就**不重跑**——这是「不偷钱」的核心。"""
    if view.last_run_at is None:
        return LoadDecision(run=True, state="missing")
    if signature(params) != view.last_signature:
        return LoadDecision(
            run=False, state="inputs_changed", inputs_changed=True,
            message="筛选条件已变更，当前结果来自旧条件；请点「按新条件重跑」")
    return None


def _gate_age(view: ViewState, now: float, max_age_s: int) -> LoadDecision:
    """时效门：``0`` 恒跑、``<0`` 永不跑、否则超龄才跑。"""
    if max_age_s == ALWAYS_REFRESH:
        return LoadDecision(run=True, state="stale")
    if max_age_s < 0:
        return LoadDecision(run=False, state="fresh")
    assert view.last_run_at is not None
    if now - view.last_run_at > max_age_s:
        return LoadDecision(run=True, state="stale")
    return LoadDecision(run=False, state="fresh")


def decide(
    *,
    view: ViewState,
    params: dict[str, Any] | None,
    now: float,
    max_age_s: int = DEFAULT_MAX_AGE_S,
    cost: CostClass = CostClass.AUTO,
    has_result: bool = True,
    force: bool = False,
) -> LoadDecision:
    """决定这次访问该不该跑。

    判定顺序（顺序即语义）：

    1. 前置条件未满足 → ``needs_setup``（不跑，也不花钱）。
       **``force`` 也不能绕过**：没凭证时强制重跑只会得到一个必然失败的请求。
    2. ``force`` → 跑（用户显式要求，绕过其余自动判定）
    3. 本次访问已自动尝试过 → 不重复跑（「最多一次」）
    4. ``Manual`` → 不自动跑
    5. 没有结果 → 跑
    6. 参数变了 → **不跑**，提示「结果来自旧条件」
    7. ``max_age`` 判定
    """
    if (early := _gate_setup(view, force)) is not None:
        return early
    if cost is CostClass.MANUAL:
        return LoadDecision(run=False, state="manual",
                            message="该操作会消耗较多算力，请确认后再执行")
    if not has_result:
        return LoadDecision(run=True, state="missing")
    if (inputs := _gate_inputs(view, params)) is not None:
        return inputs
    return _gate_age(view, now, max_age_s)
