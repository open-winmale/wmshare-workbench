"""工具层共用的取数/信封辅助。

**为什么把它放在 ``tools/_shared``**：九个 handler 都要做同一件事——
「参数校验 → hub 取数（单飞+缓存）→ 包装信封 → 错误分级」。
如果每个 handler 各写一遍，最先漂移的会是错误分级（谁把 ``QuotaError``
映射成 ``retry`` 就会让用户在额度耗尽时反复点重试）。

依赖方向：``tools → client`` 是允许的（``baselines/imports.json``），
但 **``tools/_shared`` 不得 import 任何具体工具**——它只被工具调用。

``_shared`` 不是工具：它没有 ``handler.py``，``check_envelope`` 不会扫它，
所以这里的信封构造统一走 ``core.envelope`` 的函数，不手写字面量。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

from ..core.envelope import EcEstimate, error_envelope, ok_envelope

__all__ = [
    "ToolError",
    "apply_guards",
    "as_of_of",
    "as_records",
    "bad_params",
    "cache_key",
    "cost_of",
    "envelope_from",
    "err_from",
    "fetch",
    "int_param",
    "non_negative_guards",
    "require",
    "str_param",
    "str_list_param",
]


class ToolError(Exception):
    """handler 内的可预期失败（映射为信封 + 处置动作）。"""

    def __init__(self, message: str, *, code: str = "",
                 action: str = "fix_input") -> None:
        super().__init__(message)
        self.code = code
        self.action = action


# --------------------------------------------------------------------------
# 参数
# --------------------------------------------------------------------------

def require(params: dict[str, Any], name: str) -> Any:
    """取必填参数；缺失时抛可读错误（而不是让下游 KeyError）。"""
    if name not in params or params[name] in (None, ""):
        raise ToolError(f"缺少必填参数 {name}", code="missing_param")
    return params[name]


def str_param(params: dict[str, Any], name: str, default: str = "",
               *, max_len: int = 64) -> str:
    raw = params.get(name, default)
    text = str(raw if raw is not None else default).strip()
    if len(text) > max_len:
        raise ToolError(f"参数 {name} 过长（上限 {max_len} 字符）", code="param")
    return text


def int_param(params: dict[str, Any], name: str, default: int,
              *, lo: int = 1, hi: int = 1000) -> int:
    """整数参数并**钳到合法区间**——越界不是错误，是用户的粗略意图。"""
    raw = params.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ToolError(f"参数 {name} 必须是整数，收到 {raw!r}",
                        code="param") from None
    return max(lo, min(hi, value))


def str_list_param(params: dict[str, Any], name: str,
                   *, limit: int = 500) -> list[str]:
    """字符串列表参数（接受 ``a,b`` 逗号串或 JSON 数组）。

    **去重且保序**：重复代码会让批量接口返回重复行，而用户以为自己列了两只。
    """
    raw = params.get(name)
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        items = [p.strip() for p in raw.replace("，", ",").split(",")]
    elif isinstance(raw, list):
        items = [str(p).strip() for p in raw]
    else:
        raise ToolError(f"参数 {name} 必须是字符串或数组", code="param")
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    if len(out) > limit:
        raise ToolError(
            f"参数 {name} 有 {len(out)} 项，超过上限 {limit}；请分批",
            code="limit")
    return out


def cache_key(target: str, params: dict[str, Any]) -> str:
    """主题键：``target:sha1(params)[:12]``。

    用哈希而不是拼参数，是为了让「同输入同 key」成为**结构保证**而非
    字符串拼接的正确性问题（拼接口最经典的 bug 是分隔符碰撞：
    ``a=1,b=2`` 与 ``a=1,b,2`` 拼出同一个串）。
    """
    raw = json.dumps(params, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{target}:{digest}"


# --------------------------------------------------------------------------
# 形状归一
# --------------------------------------------------------------------------

def as_records(raw: Any) -> list[dict[str, Any]]:
    """DataFrame / list / dict → ``list[dict]``。**唯一的归一实现**。

    组合门面的返回类型**随数据路径而变**：服务端聚合走 DataFrame、直读走
    list、单行场景给 dict。不统一的话前端在真实模式会拿到一个没有 ``.length``
    的对象，整页空白——而离线夹具走的是 list，永远暴露不出这个问题。

    **必须只有这一份**：此前 markets / equity.dividend / equity.indicators /
    equity.statements 各写了一遍，四份语义还有细微差别（是否把 dict 包成
    单元素列表）。同一个坑修四次、漏一次就复发，所以收到这里
    （`PROJECT_SPEC` 允许的唯一共用工具模块，见 ``check_layers`` 的
    ``SHARED_TOOL_MODULES``）。

    用鸭子类型 ``to_dict("records")`` 判断 DataFrame，**不 import pandas**：
    运行期零第三方依赖是本项目的硬约束。
    """
    if raw is None:
        return []
    to_records = getattr(raw, "to_dict", None)
    if callable(to_records):
        try:
            records = to_records("records")
        except (TypeError, ValueError):
            records = None
        if isinstance(records, list):
            return [r for r in records if isinstance(r, dict)]
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    # 单行场景（如 `forecast.snapshot` 的某一块）也当一行处理：
    # 返回空列表会让调用方把「有一行」当成「没有」。
    if isinstance(raw, dict):
        return [raw]
    return []


#: K 线行的合法字段（``kline.query_bars`` 实测字段，2026-11-25）。
#: ``sas`` 是上游数据集标识，对用户无意义，不透传。
BAR_FIELDS: tuple[str, ...] = ("date", "open", "high", "low", "close",
                               "volume", "amount", "percent")


def normalize_bars(raw: Any) -> tuple[list[dict[str, Any]], int]:
    """K 线行归一 →（日期**升序**的行表, 因缺 OHLC 被丢掉的行数）。

    两个入口共用（``equity/bars`` 分区与 ``backtest`` 价格图），**必须只有
    这一份**——归一散在两处必然漂移（``as_records`` 的教训）。

    - 形状随数据路径变：目录函数给 list、``cli.kline.bars`` 门面给
      DataFrame——先过 ``as_records``。
    - **真实 ``kline.query_bars`` 返回是新→旧**，``cli.kline.bars`` 与测试
      形状夹具是旧→新；图表需要旧→新，这里统一排序，两种口径不再外泄。
    - 缺日期或缺 OHLC 的行整行丢弃并计数（图表**不画假实体**，但调用方
      要把丢行数如实显示出来，不许静默）。
    - 日期相同的行不稳定排序无妨：同一交易日不会有两根日线。

    **调用方注意**：``as_of_of`` 取列表 ``[-1]`` 当数据截至日——归一前对
    新→旧的真实返回会把**最旧一天**当 as_of。升序归一后 ``[-1]`` 恰是
    最新一根，所以请用归一后最后一行的日期覆盖信封 ``as_of``。
    """
    rows: list[dict[str, Any]] = []
    skipped = 0
    for rec in as_records(raw):
        ohlc = (rec.get("open"), rec.get("high"), rec.get("low"), rec.get("close"))
        if not str(rec.get("date") or "") or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in ohlc):
            skipped += 1
            continue
        rows.append({k: rec.get(k) for k in BAR_FIELDS})
    rows.sort(key=lambda r: str(r["date"]))
    return rows, skipped


# --------------------------------------------------------------------------
# 取数
# --------------------------------------------------------------------------

def fetch(ctx: Any, target: str, params: dict[str, Any], *,
          force: bool = False, expensive: bool = False,
          facade: tuple[str, str] | None = None) -> tuple[Any, str]:
    """经 hub 取数（单飞 + 缓存 + last-known-good），返回 ``(值, as_of)``。

    **所有工具页都必须走这里**——绕过 hub 直接调 ``fetcher`` 会让单飞与
    退避失效，而这些是「不烧配额」的全部依据（``PROJECT_SPEC`` §4）。

    ``facade=(namespace, method)`` 用于**组合门面**（``screener.query`` /
    ``backtest.run``）：那类入口在目录里没有名字，必须走
    ``client.<namespace>.<method>()``，``client.call()`` 会抛
    ``CatalogError: 未知函数``。演示态下 FakeFetcher 也实现同名方法，
    因此两条路径在两种模式下都合法。

    :param target: 目录函数名；走门面时仅作缓存键与日志标识
    """
    hub = getattr(ctx, "hub", None)
    fetcher = getattr(ctx, "fetcher", None)
    if fetcher is None:
        raise ToolError("取数器未初始化", code="internal", action="report")

    def _produce() -> tuple[Any, str]:
        if facade is not None:
            ns, method = facade
            value = fetcher.facade(ns, method, **params)
        else:
            value = fetcher.call(target, **params)
        return value, as_of_of(value)

    if hub is None:
        return _produce()
    entry = hub.get(cache_key(target, params), _produce,
                    force=force, expensive=expensive)
    if entry.error and not entry.has_value:
        # 从未成功过：把上游异常如实抛给上层做分级
        raise ToolError(entry.error, code="upstream", action="retry")
    return entry.value, entry.as_of


def as_of_of(value: Any) -> str:
    """从返回值里猜数据截至日（信封 ``as_of`` / 行内 ``date`` / ``kline_date``）。"""
    if isinstance(value, dict):
        for key in ("as_of", "kline_date", "date", "trading_day", "quote_date"):
            got = value.get(key)
            if isinstance(got, str) and got:
                return got[:10]
        data = value.get("data")
        if isinstance(data, dict):
            return as_of_of(data)
    if isinstance(value, list) and value:
        return as_of_of(value[-1])
    return ""


# --------------------------------------------------------------------------
# 信封
# --------------------------------------------------------------------------

def cost_of(fetcher: Any, target: str,
            params: dict[str, Any]) -> EcEstimate:
    """成本预估；无模型时返回 ``model`` 说明 + ``pred_*`` 为 ``None``。

    **不在这里把 ``None`` 改成 0**——0 会被读成「免费」。

    **也不按访问方式短路**：让取数器自己回答（无模型时 ``pred_*`` 为
    ``None``、``model`` 说明原因）。handler 里特判访问方式
    会让「超预算」这条路径在离线测试无法覆盖，而预算闸恰恰是最该被测的。
    """
    if fetcher is None:
        return EcEstimate(model="none")
    try:
        raw = fetcher.cost_estimate(target, **params)
    except Exception as exc:  # noqa: BLE001 - 估算失败不该阻断主流程
        return EcEstimate(model=f"unavailable:{type(exc).__name__}")
    lo, hi = raw.get("ec_lo"), raw.get("ec_hi")
    return EcEstimate(
        pred_lo=int(lo) if isinstance(lo, (int, float)) else None,
        pred_hi=int(hi) if isinstance(hi, (int, float)) else None,
        model=str(raw.get("model") or "none"))


def envelope_from(ctx: Any, payload: Any, *, target: str = "",
                  params: dict[str, Any] | None = None,
                  as_of: str = "", meta: dict[str, Any] | None = None,
                  warnings: list[str] | None = None) -> dict[str, Any]:
    """成功信封。``as_of`` 缺省时从 payload 里推。"""
    fetcher = getattr(ctx, "fetcher", None)
    ec = cost_of(fetcher, target, params or {}) if target else EcEstimate(
        model="local")
    return ok_envelope(
        payload,
        as_of=as_of or as_of_of(payload),
        meta=meta or {},
        freshness="fresh",
        warnings=warnings,
        ec=ec)


def err_from(ctx: Any, exc: BaseException) -> dict[str, Any]:
    """异常 → 失败信封（含处置动作）。

    ``QuotaError`` 必须映射为 ``topup`` 且**不可重试**——它是终态；
    映射成 ``retry`` 会让用户在额度耗尽时反复点重试，永远失败。

    ``ctx`` 参数仅为保持全 handler 统一调用形状（``err_from(ctx, exc)``）；
    错误信封本身不携带 as_of——失败响应没有「数据截至日」可言。
    """
    action, code = classify_exc(exc)
    return error_envelope(message=str(exc) or type(exc).__name__,
                          code=code, action=action,
                          ec=EcEstimate(model="unknown"))


def classify_exc(exc: BaseException) -> tuple[str, str]:
    """``(action, code)``。顺序有意义：``QuotaError`` 是 ``LimitError`` 子类。"""
    name = type(exc).__name__
    if isinstance(exc, ToolError):
        return exc.action, exc.code or "tool_error"
    if name == "QuotaError":
        return "topup", "quota"
    if name == "NotReadyError":
        return "config", "not_ready"
    if name in ("AuthError", "ConfigError"):
        return "config", name.lower()
    if name == "UsageError":
        return "fix_input", "usage"
    if name in ("LimitError", "RateLimited", "RateLimitError"):
        return "retry", "rate_limited"
    if name in ("TransportError", "ServerError", "ConnectionError", "TimeoutError"):
        return "retry", "transient"
    if name in ("DataError", "CatalogError"):
        return "fix_input", "data"
    return "report", "unexpected"


def bad_params(message: str, code: str = "param") -> dict[str, Any]:
    """参数错误的快捷信封（不需要 ctx 的场景）。"""
    return error_envelope(message=message, code=code, action="fix_input")


#: 供 handler 直接引用的类型别名（避免每处重复写 Callable 签名）
Handler = Callable[[Any, dict[str, Any]], dict[str, Any]]


# --------------------------------------------------------------------------
# 表达式非负守卫（选股 handler 与 AI 助手执行器共用；放这里是因为
# ``check_layers`` 只允许工具经 ``_shared`` 共享代码）
# --------------------------------------------------------------------------

#: 指标码：``$PE_TTM`` 这类 token（字母/下划线开头，字母数字下划线）。
_METRIC_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
#: 布尔标志位不适用 ``>0`` 守卫（``!$IS_ST`` 与 ``$IS_ST > 0`` 会互斥）。
_FLAG_PREFIXES = ("IS_",)
#: 零值是合法「好」值的比率：排除负值但保留 0（含 -1e-6 内的浮点零）。
_ZERO_GOOD = frozenset({"GW_RATE_LAST", "IBD_RATE_LAST"})


def non_negative_guards(where: str, order: str) -> list[str]:
    """从 where/order 引用的指标生成非负守卫（保序去重）。

    普通指标追加 ``$X > 0``；布尔标志位（``IS_*``/被 ``!`` 取反的码）跳过；
    零值合法的比率（商誉/有息负债）用 ``>= -1e-6`` 排除负值、保留 0。
    用户显式写过同一守卫的指标不重复追加。
    （背景：亏损股的 ``PE_TTM`` 是负数，``$PE_TTM < 15`` 会把亏得最狠的
    公司排进「低估值」；但 ``!$IS_ST`` 不能被 ``$IS_ST > 0`` 打死。）
    """
    codes: list[str] = []
    for text in (where, order):
        for code in _METRIC_RE.findall(text):
            if code not in codes:
                codes.append(code)
    guards: list[str] = []
    for code in codes:
        if code.startswith(_FLAG_PREFIXES) or f"!${code}" in where:
            continue
        clause = (f"${code} >= -0.000001" if code in _ZERO_GOOD
                  else f"${code} > 0")
        if clause not in where:
            guards.append(clause)
    return guards


def apply_guards(where: str, guards: list[str]) -> str:
    """把守卫追加到表达式。**先加括号再 && **——
    ``$A || $B && $X > 0`` 的优先级会把守卫变成摆设。"""
    if not guards:
        return where
    return f"({where}) && " + " && ".join(guards)
