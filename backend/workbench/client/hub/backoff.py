"""错误分级与退避：决定「这个失败该不该重试」。

**这是数据面最容易被写错的地方**：把「额度耗尽」当网络抖动重试，会白烧一小时
配额并在最后仍然失败；把「限流」当终态放弃，会让一次瞬时抖动变成用户可见的
错误。wmshare 的错误层次里 ``QuotaError`` 是 ``LimitError`` 的子类——**必须
先判子类**，否则 ``except LimitError`` 会把终态当可重试。

分级依据 ``wmshare.errors`` 与 ``client.py`` 的实测常量：

| 异常 | 处置 | 理由 |
|---|---|---|
| ``QuotaError`` | **终态**（``action="topup"``） | 额度耗尽重试无效，只能充值/换凭证 |
| ``LimitError(code="rate_limited")`` | 按 ``retry_after`` 退避 | 服务端给了明确等待时间 |
| ``LimitError(code="ip_rate_limited"/"pool_unavailable")`` | 长退避 ≥60s | 共享额度，紧循环更糟 |
| ``LimitError(code="limit"/"range")`` | **终态**（``action="fix_input"``） | 参数超限，重试不会变 |
| ``TransportError`` / ``ServerError`` | 可重试，指数退避 | 瞬时故障 |
| ``UsageError`` / ``CatalogError`` | 终态（``fix_input``） | 调用方写错了 |
| ``AuthError`` | 终态（``config``） | 凭证问题 |
| ``DataError`` | **终态且不隐蔽**（``report``） | 数据完整性问题，重试只会重复拿到坏数据 |
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "RETRY_DELAYS",
    "MAX_DELAY_S",
    "JITTER",
    "LONG_FLOOR_S",
    "RetryDecision",
    "classify",
    "delay_for_attempt",
    "jittered",
]

#: 指数退避序列（秒）。超过长度后一直用最后一档。
RETRY_DELAYS: tuple[float, ...] = (2.0, 5.0, 15.0, 60.0, 300.0)

#: 单档上限（防止服务端给一个荒唐的 Retry-After 把请求挂死）。
MAX_DELAY_S: float = 600.0

#: 抖动幅度 ±10%（避免多面板同刻重试打成一波）。
JITTER: float = 0.10

#: 共享额度类错误的退避地板（秒）——服务端不告诉我们何时恢复。
LONG_FLOOR_S: float = 60.0

Action = Literal["retry", "topup", "config", "fix_input", "report", "fail"]


@dataclass(frozen=True)
class RetryDecision:
    """一次失败的处置决定。"""

    retryable: bool
    #: 建议等待秒数；``retryable=False`` 时为 0
    delay_s: float
    #: 是否终态（调用方应停止重试并上报）
    terminal: bool
    #: UI 应展示哪个按钮
    action: Action
    #: 面向用户的解释（中文，可直接显示）
    reason: str
    #: 服务端原始 code（若有）
    code: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "retryable": self.retryable,
            "delay_s": self.delay_s,
            "terminal": self.terminal,
            "action": self.action,
            "reason": self.reason,
            "code": self.code,
        }


def _terminal(action: Action, reason: str, code: str = "") -> RetryDecision:
    return RetryDecision(retryable=False, delay_s=0.0, terminal=True,
                         action=action, reason=reason, code=code)


def _retry(delay: float, reason: str, code: str = "") -> RetryDecision:
    return RetryDecision(retryable=True, delay_s=delay, terminal=False,
                         action="retry", reason=reason, code=code)


def classify(exc: BaseException, attempt: int = 0) -> RetryDecision:
    """把异常分类成处置决定。

    ``attempt`` 是「已经失败了几次」（0 基），用于算指数退避档位。

    **顺序敏感**：``QuotaError`` 是 ``LimitError`` 子类，必须先在
    ``LimitError`` 之前判断——否则额度耗尽会被当成可重试。
    """
    # 延迟导入：wmshare 是可选运行时依赖，门禁/单测不该因为它缺失而崩
    try:
        from wmshare import errors as we
    except ImportError:  # pragma: no cover - 演示与开发环境
        return _terminal("report", f"未预期的错误：{type(exc).__name__}: {exc}")

    for matcher in (_quota, _limit, _transient, _caller, _data):
        decision = matcher(we, exc, attempt)
        if decision is not None:
            return decision
    # 兜底：不认识的异常不重试（宁可让人看错误，也不静默重试掩盖问题）
    return _terminal("report", f"未预期的错误：{type(exc).__name__}: {exc}", "")


def _code(exc: BaseException) -> str:
    return str(getattr(exc, "code", "") or "")


def _quota(we: Any, exc: BaseException, attempt: int) -> RetryDecision | None:
    """额度类必须第一个判定（它是 ``LimitError`` 子类）。"""
    if not _is(we, "QuotaError", exc):
        return None
    return _terminal("topup", "取数额度已耗尽，重试无效；请充值或更换凭证", _code(exc))


def _limit(we: Any, exc: BaseException, attempt: int) -> RetryDecision | None:
    if not _is(we, "LimitError", exc):
        return None
    code = _code(exc)
    if code == "rate_limited":
        ra = getattr(exc, "retry_after", None)
        delay = float(ra) if isinstance(ra, (int, float)) and ra > 0 \
            else delay_for_attempt(attempt)
        return _retry(min(delay, MAX_DELAY_S), f"被限流，{delay:.0f} 秒后重试", code)
    if code in ("ip_rate_limited", "pool_unavailable"):
        return _retry(max(delay_for_attempt(attempt), LONG_FLOOR_S),
                      "共享额度受限，需较长等待；建议配置自有凭证", code)
    return _terminal("fix_input",
                     f"请求超出限制（{code or 'limit'}）；请缩小范围或降低条数", code)


def _transient(we: Any, exc: BaseException, attempt: int) -> RetryDecision | None:
    if not any(_is(we, n, exc)
               for n in ("TransportError", "ServerError", "StreamResetError")):
        return None
    d = delay_for_attempt(attempt)
    return _retry(d, f"临时故障，{d:.0f} 秒后重试", _code(exc))


def _caller(we: Any, exc: BaseException, attempt: int) -> RetryDecision | None:
    if _is(we, "UsageError", exc) or _is(we, "CatalogError", exc):
        return _terminal("fix_input", f"调用参数有误：{exc}", _code(exc))
    if _is(we, "AuthError", exc):
        return _terminal("config", "凭证无效或权限不足；请检查配置", _code(exc))
    return None


def _data(we: Any, exc: BaseException, attempt: int) -> RetryDecision | None:
    if not _is(we, "DataError", exc):
        return None
    return _terminal("report", f"数据完整性检查未通过：{exc}", _code(exc))


def _is(we: Any, name: str, exc: BaseException) -> bool:
    cls = getattr(we, name, None)
    return cls is not None and isinstance(exc, cls)


def delay_for_attempt(attempt: int) -> float:
    """第 ``attempt`` 次失败（0 基）后的等待秒数，未加抖动。

    序列 ``2, 5, 15, 60, 300``，之后保持 300（并受 ``MAX_DELAY_S`` 约束）。
    """
    if attempt < 0:
        attempt = 0
    idx = min(attempt, len(RETRY_DELAYS) - 1)
    return min(RETRY_DELAYS[idx], MAX_DELAY_S)


def jittered(delay: float, rand: float) -> float:
    """给延迟加 ±10% 抖动。``rand`` 是 [0,1) 的随机数（注入以便测试）。"""
    factor = 1.0 + (rand * 2.0 - 1.0) * JITTER
    return max(0.0, min(delay * factor, MAX_DELAY_S))
