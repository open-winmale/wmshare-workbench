"""``/api/economics/run``：宏观时序与收益率曲线。

三个数据面各自独立的失败域：宏观序列、汇率、国债曲线。任一取不到
**不影响其它两个**——全页失败是很糟的体验，因为用户通常只看其中一块。

**收益率曲线不推断期限**：只画服务端真的披露了的期限。用插值补出
「7 年」会让曲线看起来连续，而那个点根本不存在，据此做的久期判断是错的。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import err_from, fetch, int_param, str_param

__all__ = ["handle", "MACRO_CODES", "CURVE", "TENORS"]

#: 可选宏观指标（码与中文名）。**只列已确认存在的码**——码写错了
#: 会返回空序列，而用户看到的是「这个指标没数据」，很难与「码拼错」区分。
MACRO_CODES: tuple[tuple[str, str], ...] = (
    ("$CPI", "居民消费价格指数"),
    ("$PPI", "工业生产者出厂价格指数"),
    ("$M1", "M1 货币供应"),
    ("$M2", "M2 货币供应"),
    ("$GDP", "国内生产总值"),
    ("$PMI", "制造业 PMI"),
)

#: 收益率曲线（曲线名须与服务端披露名逐字一致）。
CURVE = "中债国债收益率曲线"

#: 可展示的期限列名。
TENORS: tuple[str, ...] = ("1年", "3年", "5年", "7年", "10年", "30年")


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    code = str_param(params, "code") or "$CPI"
    n = int_param(params, "n", 12, lo=1, hi=10)     # macro.query 实际上限 10 期
    warnings: list[str] = []

    series, series_note = _series(ctx, code, n, warnings)
    curve, curve_note = _curve(ctx, warnings)
    fx, fx_note = _fx(ctx, warnings)

    if not any((series, curve, fx)):
        # 全都取不到才整体失败
        return err_from(ctx, RuntimeError(
            "宏观、汇率、国债曲线三块数据都未取到；请检查凭证与网络"))

    return ok_envelope(
        {
            "code": code,
            "codes": [{"code": c, "label": lbl} for c, lbl in MACRO_CODES],
            "series": series,
            "series_note": series_note,
            "curve": curve,
            "curve_note": curve_note,
            "fx": fx,
            "fx_note": fx_note,
            "tenors": list(TENORS),
            "curve_name": CURVE,
        },
        as_of=_latest_date(series, fx),
        meta={"note": "收益率曲线只含服务端披露的期限，未做插值"},
        freshness="fresh",
        ec=EcEstimate(model="macro_series"),
        warnings=warnings)


def _series(ctx: Any, code: str, n: int,
            warnings: list[str]) -> tuple[list[dict[str, Any]], str]:
    """宏观时序点（**sas 升序**——图表要旧→新，真实上游给新→旧，这里归一）。

    真实 ``macro.query``（目录函数）返回**扁平 dict**：series 在顶层、
    无 ``data`` 信封、点为新→旧（2026-11-26 实测）；旧夹具曾按信封形+
    旧→新捏，双重失真导致真实模式序列块恒「返回结构异常」（D-27）。
    **未知码不报错**：真实上游返回 value 全 ``None`` 的骨架点，如实归为
    「无可用值」。
    """
    try:
        raw, _ = fetch(ctx, "macro.query", {"code": code, "n": n})
    except Exception as exc:  # noqa: BLE001 - 单块失败不拖垮整页
        warnings.append(f"宏观序列读取失败：{exc}")
        return [], "读取失败"
    points, data = _extract_series(raw)
    if not points:
        return [], "该指标无可用值（码可能不存在）"
    latest = data.get("latest") or {}
    note = f"{data.get('frequency') or '?'} 频 · 最新 {latest.get('sas') or '—'}"
    return [{"sas": p.get("sas"), "value": p.get("value")} for p in points], note


def _extract_series(raw: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """提取 series 点并按 ``sas`` 升序归一；全 ``None`` 骨架 → 空表。

    兼容两种形状：真实扁平 dict（series 顶层）与旧的演示信封形
    （``raw["data"]``）——归一只有这一份，调用方不再各自猜测。
    """
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        data = raw if isinstance(raw, dict) else {}
    points = [p for p in (data.get("series") or []) if isinstance(p, dict)]
    points.sort(key=lambda p: str(p.get("sas") or ""))
    if points and all(p.get("value") is None for p in points):
        return [], data
    return points, data


def _curve(ctx: Any, warnings: list[str]) -> tuple[list[dict[str, Any]], str]:
    """逐期限取收益率。**缺某个期限就留空，不插值。**"""
    points: list[dict[str, Any]] = []
    missing: list[str] = []
    for tenor in TENORS:
        try:
            raw, _ = fetch(ctx, "macro.bond_curve",
                           {"curve_name": CURVE, "tenor": tenor})
        except Exception:  # noqa: BLE001 - 单个期限失败不该终止
            missing.append(tenor)
            continue
        value = _curve_value(raw)
        if value is None:
            missing.append(tenor)
            continue
        points.append({"tenor": tenor, "yield": value})
    if missing:
        warnings.append(f"收益率曲线缺期限：{'、'.join(missing)}"
                        f"（服务端未披露，未做插值）")
    note = (f"披露 {len(points)}/{len(TENORS)} 个期限"
            if points else "无可用期限")
    return points, note


def _curve_value(raw: Any) -> float | None:
    """曲线返回形态可能是裸 float，也可能是带 ``value`` 的映射。"""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, dict):
        value = raw.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _fx(ctx: Any, warnings: list[str]) -> tuple[list[dict[str, Any]], str]:
    try:
        raw, _ = fetch(ctx, "fx.list", {})
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"汇率清单读取失败：{exc}")
        return [], "读取失败"
    if not isinstance(raw, list):
        return [], "返回结构异常"
    rows = [{"ccy": r.get("ccy"), "date": r.get("date"),
             "middle": r.get("middle")}
            for r in raw if isinstance(r, dict)]
    return rows, f"{len(rows)} 个币种" if rows else "无在库币种"


def _latest_date(series: list[dict[str, Any]],
                 fx: list[dict[str, Any]]) -> str:
    """取各块里最接近今天的日期（宏观只有 ``2026:M10`` 这种期点，不强行转日期）。"""
    dates = [str(r.get("date") or "") for r in fx]
    dates = [d for d in dates if d]
    return max(dates) if dates else ""
