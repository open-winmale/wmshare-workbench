"""信封契约（唯一代码真源）。

设计要点：在 wmshare 的 ``{ok, as_of, data, meta}`` 之上**只追加**三键
（``freshness`` / ``warnings`` / ``ec``），不改动原四键语义——因此任何 wmshare
返回值可以直接包装成本信封，无需转换层。规范见 ``docs/ENVELOPE.md``。

两条硬约束（由 ``tools/check_envelope.py`` 机械校验）：

1. ``ok=False`` 时 ``data`` **必须为** ``{}``。失败原因一律进 ``meta``。
   理由：消费方拿到 ``data`` 就渲染；若混入错误对象，表格会渲染出一行
   ``error: ...``，比白屏更难排查。
2. 无成本模型时 ``ec.pred_lo`` / ``ec.pred_hi`` 为 ``None``，**禁止写 0**。
   理由：0 是「免费」，``None`` 是「不知道」；混同会让用户误判成本。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "ENVELOPE_VERSION",
    "ENVELOPE_FIELDS",
    "FRESHNESS_VALUES",
    "EC_FIELDS",
    "Freshness",
    "EcEstimate",
    "build",
    "ok_envelope",
    "error_envelope",
    "wrap_upstream",
]

#: 信封版本。改动字段集必须同时改 ``docs/ENVELOPE.md`` 与基线，见规范 §3。
ENVELOPE_VERSION = 1

#: 契约字段集（顺序即 ``build`` 的输出顺序；基线文件按此校验）。
ENVELOPE_FIELDS: tuple[str, ...] = (
    "ok",
    "as_of",
    "data",
    "meta",
    "freshness",
    "warnings",
    "ec",
)

#: ``freshness`` 的合法取值。阈值来源见 ``docs/ENVELOPE.md`` §2.2。
FRESHNESS_VALUES: tuple[str, ...] = ("fresh", "stale", "expired", "unknown")

#: ``ec`` 子结构字段集。
EC_FIELDS: tuple[str, ...] = ("pred_lo", "pred_hi", "actual", "model")

#: 失败时 UI 可采取的处置动作（决定错误态显示哪个按钮）。
#: 与 wmshare 的错误分级对齐：``QuotaError`` → ``topup``；
#: ``rate_limited`` → ``retry``；``UsageError`` → ``fix_input``。
ERROR_ACTIONS: tuple[str, ...] = (
    "retry",        # 可重试（网络/限流，退避后再试）
    "topup",        # 额度耗尽，需充值或换凭证
    "config",       # 配置缺失（凭证/参数/兄弟仓）
    "fix_input",    # 用户输入有误
    "report",       # 该报 bug
)

#: 工具注册表：``slug → {method, path, summary}``。
#: 这是前后端唯一的端点清单真源——``gates/gen_contract.py`` 据此生成
#: ``frontend/src/api/contract.ts``，前端**不得**手写端点字符串。
#: 新增工具必须在此登记，否则前端没有对应类型（``check_contract`` 会红）。
ENDPOINTS: dict[str, dict[str, str]] = {
    "appinfo": {"method": "GET", "path": "/api/appinfo",
                "summary": "版本/演示态/凭证状态"},
    "tools": {"method": "GET", "path": "/api/tools", "summary": "工具注册表"},
    "health": {"method": "GET", "path": "/api/health",
               "summary": "hub/db/wmshare 三态"},
    "sources": {"method": "POST", "path": "/api/sources/run",
                "summary": "数据源与新鲜度总览"},
    "watchlist": {"method": "POST", "path": "/api/watchlist/run",
                  "summary": "自选批量行情"},
    "markets": {"method": "POST", "path": "/api/markets/run",
                "summary": "行情表与 KPI"},
    "economics": {"method": "POST", "path": "/api/economics/run",
                  "summary": "宏观时序与曲线"},
    "backtest": {"method": "POST", "path": "/api/backtest/run",
                 "summary": "单标的回测"},
    "dashboard": {"method": "POST", "path": "/api/dashboard/run",
                  "summary": "每日驾驶舱"},
    "screener": {"method": "POST", "path": "/api/screener/run",
                 "summary": "条件选股"},
    "equity": {"method": "POST", "path": "/api/equity/run",
               "summary": "个股研究"},
    "portfolio": {"method": "POST", "path": "/api/portfolio/run",
                  "summary": "持仓账本"},
    "ec_estimate": {"method": "POST", "path": "/api/ec/estimate",
                    "summary": "EC 试算"},
    "key": {"method": "POST", "path": "/api/key", "summary": "热切凭证"},
    "assistant": {"method": "GET", "path": "/api/assistant/info",
                  "summary": "AI 助手：配置状态与领域清单"},
    "assistant_chat": {"method": "POST", "path": "/api/assistant/chat",
                       "summary": "AI 助手：发起一轮提问（返回 job_id）"},
    "assistant_stream": {"method": "GET", "path": "/api/assistant/stream",
                         "summary": "AI 助手：轮询任务进度与部分结果"},
    "assistant_stop": {"method": "POST", "path": "/api/assistant/stop",
                       "summary": "AI 助手：停止运行中的任务"},
    "assistant_sessions": {"method": "GET", "path": "/api/assistant/sessions",
                           "summary": "AI 助手：会话列表"},
    "assistant_session": {"method": "POST", "path": "/api/assistant/session",
                          "summary": "AI 助手：读取或删除一个会话"},
}

Freshness = Literal["fresh", "stale", "expired", "unknown"]


@dataclass(frozen=True)
class EcEstimate:
    """一次取数的成本预估与实际。

    ``pred_lo`` / ``pred_hi`` 为 ``None`` 表示**无成本模型**（不是免费）。
    """

    pred_lo: int | None = None
    pred_hi: int | None = None
    actual: int | None = None
    model: str = "none"

    @property
    def known(self) -> bool:
        """是否有成本模型。"""
        return self.pred_lo is not None or self.pred_hi is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "pred_lo": self.pred_lo,
            "pred_hi": self.pred_hi,
            "actual": self.actual,
            "model": self.model,
        }


@dataclass(frozen=True)
class Envelope:
    """信封的不可变形态（便于测试与相等断言）。"""

    ok: bool
    as_of: str = ""
    data: Any = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    freshness: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    ec: EcEstimate | None = None

    def __post_init__(self) -> None:
        if self.freshness not in FRESHNESS_VALUES:
            raise ValueError(
                f"freshness 非法：{self.freshness!r}；"
                f"应为 {FRESHNESS_VALUES} 之一")
        if not self.ok and self.data != {}:
            raise ValueError(
                "ok=False 时 data 必须为 {}（失败原因请放进 meta）；"
                f"收到 {type(self.data).__name__}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "as_of": self.as_of,
            "data": self.data,
            "meta": self.meta,
            "freshness": self.freshness,
            "warnings": list(self.warnings),
            "ec": self.ec.as_dict() if self.ec is not None else None,
        }


def build(
    *,
    ok: bool,
    data: Any = None,
    as_of: str = "",
    meta: dict[str, Any] | None = None,
    freshness: str = "unknown",
    warnings: list[str] | None = None,
    ec: EcEstimate | None = None,
) -> dict[str, Any]:
    """构造信封字典（门面统一出口）。

    ``ok=False`` 时无论传入什么 ``data`` 都会被归一为 ``{}``——与其让调用方
    记着，不如让出口强制。这比在 9 个 handler 里各写一遍可靠。
    """
    env = Envelope(
        ok=bool(ok),
        as_of=str(as_of or ""),
        data={} if not ok else ({} if data is None else data),
        meta=dict(meta or {}),
        freshness=freshness,
        warnings=list(warnings or []),
        ec=ec,
    )
    return env.as_dict()


def ok_envelope(
    data: Any,
    *,
    as_of: str = "",
    meta: dict[str, Any] | None = None,
    freshness: str = "unknown",
    warnings: list[str] | None = None,
    ec: EcEstimate | None = None,
) -> dict[str, Any]:
    """成功信封的简写。"""
    return build(ok=True, data=data, as_of=as_of, meta=meta,
                 freshness=freshness, warnings=warnings, ec=ec)


def error_envelope(
    *,
    message: str,
    code: str = "",
    action: str = "report",
    as_of: str = "",
    meta: dict[str, Any] | None = None,
    freshness: str = "unknown",
    warnings: list[str] | None = None,
    ec: EcEstimate | None = None,
) -> dict[str, Any]:
    """失败信封。

    ``action`` 与 wmshare 的错误分级对齐：
    ``retry`` / ``topup`` / ``config`` / ``fix_input`` / ``report``。
    """
    m = dict(meta or {})
    m.setdefault("error", message)
    if code:
        m.setdefault("code", code)
    m.setdefault("action", action)
    return build(ok=False, as_of=as_of, meta=m, freshness=freshness,
                 warnings=warnings, ec=ec)


def wrap_upstream(
    upstream: dict[str, Any],
    *,
    freshness: str = "unknown",
    warnings: list[str] | None = None,
    ec: EcEstimate | None = None,
) -> dict[str, Any]:
    """把 wmshare 的 ``{ok, as_of, data, meta}`` 包装成本项目信封。

    只读取原四键，原样保留到 ``meta``（避免信息丢失），再补三键。
    """
    if not isinstance(upstream, dict):
        return error_envelope(
            message=f"上游返回非映射类型：{type(upstream).__name__}",
            code="upstream_shape", action="report")
    return build(
        ok=bool(upstream.get("ok")),
        data=upstream.get("data"),
        as_of=str(upstream.get("as_of") or ""),
        meta=dict(upstream.get("meta") or {}),
        freshness=freshness,
        warnings=warnings,
        ec=ec,
    )
