"""个股研究 —— 分红分区（``bonus.snapshot`` + ``bonus.query_list``）。

**一个接口给全 18 个字段**（TTM/上年/3 年均值与最低、3 年趋势、派息率、
累计与 TTM 分红、市值、PE），因此不要分开调单项接口：

``bonus.snapshot_yield_ttm`` 返回的是**裸 float**（``0.0354``），按 dict
处理会静默得到 ``{}``，页面上显示「—」。用户会以为「这只票没有分红数据」，
而数据完全可用——这是本项目反复修的那类「静默降级成缺失」。

字段口径（百分数 / 金额 / 文本）在 ``DIVIDEND_FIELDS`` 里声明，
由前端按 ``format`` 渲染：**前端不自己猜口径**，否则 0.0355 会显示成
"0.04" 而不是 "3.55%"。
"""

from __future__ import annotations

from typing import Any

from ...tools._shared import ToolError, as_records, fetch

__all__ = ["build", "DIVIDEND_FIELDS"]


def build(ctx: Any, symbol: str,
              params: dict[str, Any]) -> tuple[Any, str, list[str]]:
    """分红：``bonus.snapshot`` 一次给全 18 个字段 + 历史明细。

    **不要再分开调多个接口**（踩过）：``bonus.snapshot_yield_ttm`` 返回的是
    **裸 float**（``0.0354``）而不是字典，按 ``.yield_ttm`` 取会静默变成
    ``None``——页面显示「—」，而数据其实完全可用。

    ``bonus.snapshot`` 含 TTM/上年/3 年均值与最低、3 年趋势、派息率、
    总分红与 TTM 分红、市值。历史明细走 ``bonus.query_list``（逐次派息）。
    """
    snap, as_of = fetch(ctx, "bonus.snapshot", {"sym": symbol})
    if not isinstance(snap, dict) or not snap:
        raise ToolError(f"{symbol} 无分红快照", code="upstream", action="retry")

    warnings: list[str] = []
    history: list[dict[str, Any]] = []
    try:
        raw, _ = fetch(ctx, "bonus.query_list", {"sym": symbol})
        history = as_records(raw)
    except Exception as exc:  # noqa: BLE001 - 明细失败不影响快照
        warnings.append(f"分红历史读取失败：{exc}")

    # 键名带 `dividend_` 前缀：`fields` 已被**估值序列**分区占用（string[]），
    # 同一分区集里两个 `fields` 指两种东西，前端必读错。
    return ({"dividend_fields": _dividend_fields(snap),
             "dividend_history": _dividend_history(history)},
            as_of or str(snap.get("quote_date") or ""), warnings)


#: 分红快照要展示的字段（顺序即 UI 顺序）。值为百分数口径的单独标注。
DIVIDEND_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("yield_ttm", "TTM 股息率（%）", "pct"),
    ("payout_ttm", "TTM 派息率（%）", "pct"),
    ("dps_ttm", "每股分红 TTM（元）", "num"),
    ("yield_lyr", "上年股息率（%）", "pct"),
    ("yield_3y_avg", "3 年平均股息率（%）", "pct"),
    ("yield_3y_min", "3 年最低股息率（%）", "pct"),
    ("yield_3y_trend", "3 年趋势", "text"),
    ("bonus_total", "累计分红（元）", "money"),
    ("bonus_ttm", "TTM 分红（元）", "money"),
    ("pe_ttm", "PE(TTM)", "num"),
    ("quote_date", "行情日", "text"),
)


#: 上游趋势枚举 → 中文。**不把英文枚举直接显示给用户**。
_TREND_LABELS: dict[str, str] = {
    "valley": "低位（近 3 年谷底）",
    "peak": "高位（近 3 年峰值）",
    "flat": "平稳",
    "rising": "上行",
    "falling": "下行",
}


def _dividend_fields(snap: dict[str, Any]) -> list[dict[str, Any]]:
    """把快照摊成 ``[{key,label,value,format}]``，供前端按 format 渲染。"""
    out: list[dict[str, Any]] = []
    for key, label, fmt in DIVIDEND_FIELDS:
        if key not in snap:
            continue
        value = snap.get(key)
        if fmt == "text" and key == "yield_3y_trend":
            value = _TREND_LABELS.get(str(value), str(value))
        out.append({"key": key, "label": label, "value": value, "format": fmt})
    return out


def _dividend_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """逐次派息明细（按公告日降序，最近在前）。"""
    out = [{"announce": r.get("announce"), "ex_date": r.get("ex_div")
            or r.get("ex_date"), "record_date": r.get("record_date"),
            "sas": r.get("sas"), "dps": r.get("dps"),
            "payout_ratio": r.get("payout_ratio"), "ccy": r.get("ccy")}
           for r in rows]
    out.sort(key=lambda r: str(r.get("announce") or ""), reverse=True)
    return out


