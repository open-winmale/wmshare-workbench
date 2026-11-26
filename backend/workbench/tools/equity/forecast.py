"""个股研究 —— 业绩预告分区（``forecast.snapshot``）。

**一个接口给三块**：``yjyg``（最新业绩预告）+ ``yjkb``（最新业绩快报）+
``next_disclosure``（下次预约披露）。因此不要分开调 ``forecast.yjyg_latest``
/ ``forecast.yjkb_latest`` / ``forecast.disclosure_next`` —— 三次请求拿到的
是同一份数据的三部分，且任一块缺失时你会分不清「没有」还是「调错了」。

**上游的 ``0`` 不是「零」，是「没披露」**（实测）：
``601318`` 的 2015 年半年报预告返回 ``np_lower=0``/``np_upper=0``/``rev_lower=0``，
而同一行的 ``np_amp_lower=0.62``（+62%）是真实值。把 0 原样显示会让页面上
出现「预计净利润 0 元 ～ 0 元」，那是在陈述一个上游从未给出的事实。
本模块统一把这些字段的 0 归一成 ``None``（显示「—」）。

**预告可能是很久以前的**：茅台的最近预告报告期是 2024-12-31（公告 2025-01-03），
距行情日近两年——年报预告只在跨年时发一次，「最新预告」不一定是「近期」。
因此这里显式给出 ``age_days`` 与 ``stale`` 标注，让页面能说「这条已经过期」，
而不是把两年前的数字摆在「最新业绩预告」标题下当成当前预期。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ...tools._shared import ToolError, fetch

__all__ = ["build", "FORECAST_FIELDS", "SNAPSHOT_KEYS"]

#: 快照里的三块（顺序即 UI 顺序）。
SNAPSHOT_KEYS: tuple[tuple[str, str], ...] = (
    ("yjyg", "最新业绩预告"),
    ("yjkb", "最新业绩快报"),
    ("next_disclosure", "下次预约披露"),
)

#: 预告字段 → (中文名, 口径)。
#: 口径：money 元 · pct 小数 · num 数值 · int 计数 · text 文本。
#:
#: ``deduct_lower`` / ``deduct_upper`` 也在其中：它们**经常**是 0（上游没给
#: 扣非区间），归一成 ``None`` 后页面显示「—」而不是「0 元」。
FORECAST_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("report_date", "报告期", "text"),
    ("ann_date", "公告日", "text"),
    ("first_ann_date", "首次公告日", "text"),
    ("predict_type", "预告类型", "text"),
    ("np_lower", "净利下限", "money"),
    ("np_upper", "净利上限", "money"),
    ("np_amp_lower", "净利增幅下限", "pct"),
    ("np_amp_upper", "净利增幅上限", "pct"),
    ("np_preyear", "上年同期净利", "money"),
    ("rev_lower", "营收下限", "money"),
    ("rev_upper", "营收上限", "money"),
    ("rev_amp_lower", "营收增幅下限", "pct"),
    ("rev_amp_upper", "营收增幅上限", "pct"),
    ("deduct_lower", "扣非净利下限", "money"),
    ("deduct_upper", "扣非净利上限", "money"),
    # 计数用 `int`：`num` 会渲染成 "1.00"，把「修正 1 次」写成一个小数
    ("revised_count", "修正次数", "int"),
    ("content", "预告内容", "text"),
)

#: 快报字段 → (中文名, 口径)。
SPEED_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("report_date", "报告期", "text"),
    ("ann_date", "公告日", "text"),
    ("revenue", "营业收入", "money"),
    ("netprofit", "净利润", "money"),
    ("np_yoy", "净利同比", "pct"),
    ("rev_yoy", "营收同比", "pct"),
    ("roe", "净资产收益率", "pct"),
    ("basic_eps", "基本每股收益", "num"),
    ("bvps", "每股净资产", "num"),
    ("netprofit_ly", "上年同期净利", "money"),
    ("revenue_ly", "上年同期营收", "money"),
)

#: 数值口径里 0 恒为「未披露」的字段：预告区间与同比幅度。
#:
#: **不含 ``np_amp_*``**：增幅 0（持平）是可能的取值，不能当成缺失。
#: 但实测里区间类字段的 0 从没出现过真实含义——净利润恰好 0 元的预告
#: 区间在这种数据源上没有实际意义。
_ZERO_IS_MISSING: frozenset[str] = frozenset({
    "np_lower", "np_upper", "rev_lower", "rev_upper",
    "deduct_lower", "deduct_upper", "np_preyear",
    "revenue", "netprofit", "netprofit_ly", "revenue_ly",
    "basic_eps", "bvps", "roe",
})

#: 超过这么多天就算「陈旧预告」：A 股年报预告集中在 1 月，半年报在 7 月，
#: 因此 400 天（跨一个完整披露周期）之后仍然「最新」= 这份预告已不代表当前。
STALE_DAYS = 400


def build(ctx: Any, symbol: str,
          params: dict[str, Any]) -> tuple[Any, str, list[str]]:
    """业绩预告/快报/预约披露（一次调用取三块）。"""
    raw, as_of = fetch(ctx, "forecast.snapshot", {"sym": symbol})
    if not isinstance(raw, dict) or not raw:
        raise ToolError(f"{symbol} 无业绩披露数据", code="upstream",
                        action="retry")

    warnings: list[str] = []
    yjyg = raw.get("yjyg")
    if not isinstance(yjyg, dict) or not yjyg:
        yjyg = {}
        warnings.append("该标的近期无业绩预告（多为不需预告的情形）")

    blocks = {
        "yjyg": _fields_of(yjyg, FORECAST_FIELDS),
        "yjkb": _fields_of(raw.get("yjkb") or {}, SPEED_FIELDS),
        "next_disclosure": _next_disclosure(raw.get("next_disclosure")),
    }
    # 年龄相对**数据截至日**算，不相对系统当天：演示态的数据是 2026-11-20
    # 的静态快照，用 wall clock 算会凭空多出几天，且跨会话读数会自己变。
    age = _age_days(yjyg, _reference(as_of))
    if age is not None and age > STALE_DAYS:
        warnings.append(
            f"最新预告的报告期为 {yjyg.get('report_date')}，"
            f"距数据截至日 {age} 天——「最新」不等于「近期」，"
            f"该标的可能已不在预告义务范围内")
    return ({"forecast_blocks": _labelled(blocks),
             "yjyg_age_days": age,
             "yjyg_stale": age is not None and age > STALE_DAYS,
             "quote_date": str(raw.get("as_of") or as_of or "")},
            as_of, warnings)


def _labelled(blocks: dict[str, list[dict[str, Any]]]
              ) -> list[dict[str, Any]]:
    """三块摊成 ``[{key,title,fields,empty}]``，空块显式标 ``empty``。

    **空块也要出现**：只渲染有数据的那块会让用户以为「这页只有快报」，
    而实际上这家公司根本没发过预告。
    """
    out: list[dict[str, Any]] = []
    for key, title in SNAPSHOT_KEYS:
        fields = blocks.get(key) or []
        out.append({"key": key, "title": title, "fields": fields,
                    "empty": not fields})
    return out


def _fields_of(row: dict[str, Any],
               spec: tuple[tuple[str, str, str], ...]
               ) -> list[dict[str, Any]]:
    """按声明表摊平，0 归 ``None``。缺字段的**整行跳过**（不显示「—」占位）。"""
    if not isinstance(row, dict) or not row:
        return []
    out: list[dict[str, Any]] = []
    for key, label, fmt in spec:
        if key not in row:
            continue
        value = row.get(key)
        if key in _ZERO_IS_MISSING and _is_zero(value):
            value = None
        if value == "" and fmt == "text":
            value = None
        out.append({"key": key, "label": label, "value": value, "format": fmt})
    return out


def _next_disclosure(raw: Any) -> list[dict[str, Any]]:
    """预约披露：真实返回可能是 nil（未预约），此时空块。"""
    if not isinstance(raw, dict) or not raw:
        return []
    value = raw.get("report_date")
    if not value:
        return []
    return [{"key": "report_date", "label": "预约披露日", "value": value,
             "format": "text"}]


def _is_zero(value: Any) -> bool:
    """``0`` 与 ``0.0`` 视为「未披露」；``None``/字符串不在此列。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value == 0


def _age_days(yjyg: dict[str, Any], today: date | None) -> int | None:
    """报告期距 ``today`` 多少天。日期不合法时返回 ``None``（不猜）。"""
    if today is None:
        return None
    raw = yjyg.get("report_date")
    if not isinstance(raw, str) or len(raw) < 10:
        return None
    try:
        then = date.fromisoformat(raw[:10])
    except ValueError:
        return None
    if then > today:
        return None
    return (today - then).days


def _reference(as_of: str) -> date | None:
    """参照日：优先用**数据截至日**，取不到才退回系统当天。

    数据截至日才是「这份数据自称知道到的时点」。用 wall clock 会在数据
    停在上一交易日时制造虚假的陈旧天数，而且同一个页面隔几天再看数字
    会变——那不是数据在变，是我们的参照系在漂。
    """
    for candidate in (as_of,):
        if isinstance(candidate, str) and len(candidate) >= 10:
            try:
                return date.fromisoformat(candidate[:10])
            except ValueError:
                continue
    return date.today()
