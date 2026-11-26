"""``/api/screener/run``：条件选股 + 策略库。

四条硬约束（都对应用户真实会踩的坑）：

1. **表达式拦住 ``and``/``or``/``not``**。服务端的表达式语言是 XS 风格，
   写 Python 布尔关键字会得到一个诡异的空结果或语法错，而不是「不支持」。
   本地先拦，报错信息说明该用什么。
2. **重列成本前置**。取未物化字段会触发物化（实测 6 万 EC 量级），
   所以超过阈值时返回 ``needs_confirm`` 且**零请求**——由前端弹确认。
3. **策略可存可重跑**。存的是表达式**原文**（不是求值后的结果），
   重跑时按当前数据重新求值（非负守卫重跑时按当次开关重新追加）。
4. **非负守卫**（2026-11-27，用户：选股要顾虑掉负值）。亏损股的
   ``PE_TTM`` 是负数——``$PE_TTM < 15`` 会把亏得最狠的公司排进「低估值」。
   默认对 where/order 引用的指标追加守卫（服务端追加而不是客户端过滤：省 EC，
   被守卫挡掉的行根本不计费），并如实披露追加了什么。**布尔标志位（``IS_*``）
   跳过**（``!$IS_ST`` 与 ``$IS_ST > 0`` 会互斥）；商誉/有息负债等零值合法的
   比率用 ``>= -1e-6``，只排除负值、保留 0。用户已写过同一守卫的不重复追加。

本页不提供「推荐策略」。保存的模板只包含用户自己写过的表达式。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import (
    ToolError,
    apply_guards,
    as_records,
    cost_of,
    err_from,
    fetch,
    int_param,
    non_negative_guards,
    str_param,
)

__all__ = ["handle", "TARGET", "NEEDS_CONFIRM_EC", "FORBIDDEN_WORDS",
           "PRESET_SCREENS", "non_negative_guards", "apply_guards"]

TARGET = "screener.query"

#: 组合门面：
#: ``screener.query`` 是 SDK 客户端组合面，**不在目录里**，
#: ``client.call()`` 会抛 CatalogError。必须走 ``cli.screener.query()``。
FACADE: tuple[str, str] = ("screener", "query")

#: 预估成本超过此值时要求二次确认（零请求）。
NEEDS_CONFIRM_EC = 40_000

#: 本地拦截的 Python 布尔关键字（服务端表达式语言不支持）。
FORBIDDEN_WORDS: tuple[tuple[str, str], ...] = (
    (" and ", "&&"),
    (" or ", "||"),
    (" not ", "!"),
)

#: 内置示例表达式（**不是推荐策略**，只是语法演示 + 已确认可跑）。
PRESET_SCREENS: tuple[dict[str, str], ...] = (
    {"name": "示例：市盈率低于 15（盈利股）",
     "where": "$PE_TTM < 15 && $PE_TTM > 0"},
    {"name": "示例：站上 MA20 且非 ST", "where": "$ABOVE_MA20 == 1"},
    {"name": "示例：TTM 股息率高于 3%", "where": "$ID_BONUS_RATE_TTM > 3"},
)


def _guard_where(params: dict[str, Any], where: str,
                 order: str) -> tuple[str, list[str]]:
    """按开关产出（执行表达式, 守卫列表）。默认开，
    ``exclude_negative=False`` 显式关；保存策略不受影响（存原文）。"""
    raw = params.get("exclude_negative")
    enabled = True if raw is None else bool(raw)
    guards = non_negative_guards(where, order) if enabled else []
    return apply_guards(where, guards), guards


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    try:
        where = _expression(params)
        limit = int_param(params, "limit", 50, lo=1, hi=500)
        order = str_param(params, "order")
        fields = _fields(params)
        save_as = str_param(params, "save_as")
        confirmed = bool(params.get("confirmed"))
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    # ④ 非负守卫：默认开（exclude_negative=False 显式关）。
    #   保存策略仍存**原文**——守卫是执行口径，重跑时按当次开关重新追加。
    where_final, guards = _guard_where(params, where, order)

    call_params = {"where": where_final, "limit": limit, "desc": True}
    if order:
        call_params["order"] = order
    if fields:
        call_params["fields"] = fields

    # ② 成本前置：超阈值且未确认 → **零请求**
    estimate = _estimate(ctx, call_params)
    if (estimate.pred_hi or 0) > NEEDS_CONFIRM_EC and not confirmed:
        return _pending_confirm(ctx, where_final, estimate)

    try:
        raw, as_of = fetch(ctx, TARGET, call_params,
                           facade=("screener", "query"))
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    payload = raw if isinstance(raw, dict) else {}
    if save_as:
        _persist(ctx, save_as, where, order, fields)
    warnings: list[str] = []
    if guards:
        warnings.append("已追加非负守卫：" + "、".join(guards)
                        + "（布尔标志位跳过；零值合法的比率只排除负值；"
                          "默认开启，可在页面关掉）")
    return ok_envelope(
        {
            "needs_confirm": False,
            "where": where_final,
            "total": _total(payload),
            "rows": _rows(payload),
            "estimate": estimate.as_dict(),
            "presets": list(PRESET_SCREENS),
            "saved": _saved(ctx),
            "saved_as": save_as,
        },
        as_of=as_of,
        meta={"note": "表达式原文已保留，可保存为策略后重跑"
                      + ("（非负守卫为执行口径，不写入策略原文）" if guards else "")},
        freshness="fresh",
        ec=estimate,
        warnings=warnings)


def _pending_confirm(ctx: Any, where: str,
                     estimate: EcEstimate) -> dict[str, Any]:
    """超预算待确认信封。**此函数不发起任何上游请求**。

    单独成函数不只是为了行数：它把「零请求」这件事圈在一个不调用
    ``fetch`` 的函数里，读代码时一眼可见不会误加取数。
    """
    return ok_envelope(
        {
            "needs_confirm": True,
            "where": where,
            "estimate": estimate.as_dict(),
            "threshold": NEEDS_CONFIRM_EC,
            "message": (f"该表达式预估消耗最高 {estimate.pred_hi:,} EC，"
                        f"超过自动执行阈值 {NEEDS_CONFIRM_EC:,}。"
                        f"确认后才会发起请求（当前零请求）。"),
            "presets": list(PRESET_SCREENS),
            "saved": _saved(ctx),
        },
        as_of="",
        meta={"note": "等待用户确认；未发起任何上游请求"},
        freshness="unknown",
        ec=estimate)


def _expression(params: dict[str, Any]) -> str:
    where = str_param(params, "where", max_len=2000)
    if not where:
        raise ToolError("缺少选股表达式（where）", code="missing_param")
    lowered = f" {where.lower()} "
    for word, hint in FORBIDDEN_WORDS:
        if word in lowered:
            raise ToolError(
                f"表达式不支持 Python 关键字 {word.strip()!r}；"
                f"请改用 {hint}", code="expression")
    return where


def _fields(params: dict[str, Any]) -> list[str]:
    raw = params.get("fields")
    if not raw:
        return []
    if isinstance(raw, str):
        return [f.strip() for f in raw.replace("，", ",").split(",") if f.strip()]
    if isinstance(raw, list):
        return [str(f).strip() for f in raw if str(f).strip()]
    raise ToolError("fields 必须是字符串或数组", code="param")


def _estimate(ctx: Any, call_params: dict[str, Any]) -> EcEstimate:
    """成本预估。**不在演示模式下特判**——让取数器自己回答，
    否则「超预算」这条路径在演示态无法被测试。"""
    return cost_of(getattr(ctx, "fetcher", None), TARGET, call_params)


def _total(payload: dict[str, Any]) -> Any:
    """全市场命中数。**真实返回是统一信封**：``data.count``——
    顶层 ``rows`` 在真实模式根本不存在（此前因此恒空），旧夹具是扁平
    dict 所以全绿。读法：``data`` 优先，顶层键做旧形状回落。"""
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("count", "total", "matched"):
            if key in data:
                return data[key]
    for key in ("total", "count", "matched"):
        if key in payload:
            return payload[key]
    rows = _rows(payload)
    return len(rows) if rows else None


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """命中行。真实形状：``data.rows`` 且是 **DataFrame**（过 ``as_records``）；
    扁平 ``rows`` / 列表形 ``data`` 是旧形状回落。"""
    data = payload.get("data")
    rows = None
    if isinstance(data, dict):
        rows = data.get("rows")
    if rows is None:
        rows = payload.get("rows")
    if rows is None and isinstance(data, list):
        rows = data
    return [r for r in as_records(rows) if isinstance(r, dict)]


def _saved(ctx: Any) -> list[dict[str, Any]]:
    """已保存的策略（只读列表，详情按名取）。"""
    store = getattr(ctx, "store", None)
    if store is None:
        return []
    try:
        rows = store.list_screens()
    except Exception:  # noqa: BLE001
        return []
    return [{"name": r.get("name"), "where": r.get("where_expr"),
             "order": r.get("order_by"), "created_at": r.get("created_at")}
            for r in rows]


def _persist(ctx: Any, name: str, where: str, order: str,
             fields: list[str]) -> None:
    """保存策略。写库失败**不阻断**页面显示（结果已经在手上了）。"""
    store = getattr(ctx, "store", None)
    if store is None:
        return
    try:
        store.save_screen(name, where, order, ",".join(fields))
    except Exception:  # noqa: BLE001 - 保存失败不该让已算出的结果丢失
        return
