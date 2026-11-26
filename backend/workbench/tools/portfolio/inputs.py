"""账本工具的输入解析（成交、净值、收益序列）。

**独立成模块的理由**：handler 要处理的输入有三种来源（页面 JSON、
本地库回放、命令行），每种都要做「类型检查 + 缺省 + 排序」。
把这些塞进 handler 会让它一路涨到 300 行以上，而其中真正的业务
（五法估值）只有几行调用。

**解析原则**：能明确报错的就不帮忙猜。例如 ``shares`` 缺失直接报
「第 N 笔成交缺少股数」，而不是当 0 处理——当 0 会让这笔记账变成长度为 0
的成交，最终持仓少了一笔，用户很难发现。
"""

from __future__ import annotations

import json
from typing import Any

from ...client.ledger import Trade
from ...client.ledger.performance import CashFlow
from ...tools._shared import ToolError

__all__ = ["opt_float", "parse_flows", "parse_nav", "parse_returns",
           "parse_trades"]


def opt_float(value: Any, *, default: float | None) -> float | None:
    """``None``/``""`` 保持 ``default``；其它尽力转 float，失败给 ``None``。"""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_json(raw: Any, name: str) -> Any:
    """接受已解析的 Python 对象或 JSON 字符串。"""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ToolError(f"{name} 不是合法 JSON：{exc}", code="param") from None
    return raw


def parse_trades(raw: Any) -> list[Trade]:
    """解析成交列表并按日期排序。

    **排序是必须的**：乱序回放会让卖出找不到对应的买入批次，
    进而算出完全错误的成本基础。
    """
    items = _load_json(raw, "trades")
    if not isinstance(items, list) or not items:
        raise ToolError("缺少成交列表（trades）", code="missing_param")
    out: list[Trade] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ToolError(f"第 {i + 1} 笔成交不是对象", code="param")
        out.append(_one_trade(item, i))
    out.sort(key=lambda t: t.date)
    return out


def _one_trade(item: dict[str, Any], index: int) -> Trade:
    """单笔成交。缺关键字段时报「第 N 笔」而不是笼统的「参数错误」。"""
    label = f"第 {index + 1} 笔成交"
    for field in ("date", "code", "side"):
        if not item.get(field):
            raise ToolError(f"{label}缺少 {field}", code="param")
    try:
        return Trade(
            date=str(item["date"]),
            code=str(item["code"]),
            side=str(item["side"]),
            shares=float(item.get("shares") or 0),
            price=float(item.get("price") or 0),
            fx=opt_float(item.get("fx"), default=1.0),
            fee=float(item.get("fee") or 0),
            lot_id=str(item.get("lot_id") or ""),
        )
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{label}非法：{exc}", code="param") from None


def parse_nav(raw: Any) -> list[tuple[str, float]] | None:
    """净值序列 ``[{date, nav}]`` → ``[(date, nav)]``；非数组返回 ``None``。"""
    items = _load_json(raw, "nav")
    if not isinstance(items, list):
        return None
    out: list[tuple[str, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        date, nav = item.get("date"), item.get("nav")
        if date is None or nav is None:
            continue
        try:
            out.append((str(date), float(nav)))
        except (TypeError, ValueError):
            continue
    return out or None


def parse_flows(raw: Any) -> list[CashFlow]:
    """出入金序列 ``[{date, amount}]``。"""
    items = _load_json(raw, "flows")
    if not isinstance(items, list):
        return []
    out: list[CashFlow] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        date, amount = item.get("date"), item.get("amount")
        if date is None or amount is None:
            continue
        try:
            out.append(CashFlow(date=str(date), amount=float(amount)))
        except (TypeError, ValueError):
            continue
    return out


def parse_returns(raw: Any) -> list[float | None] | None:
    """收益序列；``None`` 保留为缺失（**不补 0**：补 0 会低估波动）。"""
    items = _load_json(raw, "returns")
    if not isinstance(items, list):
        return None
    return [opt_float(v, default=None) for v in items]
