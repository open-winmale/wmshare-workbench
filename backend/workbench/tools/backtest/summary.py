"""回测汇总数字（``summary``）的字段口径与本地现算。

**为什么单独一个文件**：``handler.py`` 有 240 行棘轮，而汇总口径的注释
本身就是知识（踩过的坑）。与 ``equity/`` 的分区模块同一做法：口径知识
放模块，handler 只做编排。

**键名必须取上游真实字段**（2026-11-26 实测）：``backtest.run`` 的
``summary`` 给的是 ``total_return`` / ``cagr`` / ``max_drawdown`` /
``sharpe`` / ``win_rate`` / ``n_trades`` / ``avg_hold_days`` /
``buy_hold_return``；``final_nav`` 与 ``total_fee`` 上游**根本不返回**，
由净值曲线末点与成交明细 ``fee`` 求和现算。

此前按 ``annual_return`` / ``trades`` / ``final_nav`` / ``total_fee``
取名，页面四项恒为「—」却没人发现——离线夹具捏的正是那几个想象出来的
键名，真实取数与夹具从没对过。``tests/test_tools.py`` 现在有一条
``test_summary_labels_all_populated`` 钉住「每个标签都要有值」。
"""

from __future__ import annotations

from typing import Any

__all__ = ["SUMMARY_LABELS", "summary"]

#: ``summary`` 的八个数字 → 中文标签与单位。
SUMMARY_LABELS: tuple[tuple[str, str, str], ...] = (
    ("total_return", "累计收益", "pct"),
    ("cagr", "年化收益", "pct"),
    ("max_drawdown", "最大回撤", "pct"),
    ("sharpe", "夏普比率", "num"),
    ("win_rate", "胜率", "pct"),
    ("n_trades", "成交笔数", "int"),
    ("final_nav", "期末净值", "money"),
    ("total_fee", "累计费用", "money"),
)


def summary(raw: Any, equity: list[dict[str, Any]], trades: list[dict[str, Any]]) -> dict[str, Any]:
    """八个汇总数字。**缺的不补 0**——缺失与「算出来是 0」不同。

    ``final_nav`` / ``total_fee`` 由本地已取到的数据现算：净值曲线末点、
    成交明细 ``fee`` 求和。二者都没有时才留空（页面渲染 ``—``）。

    ``n_trades`` 用**明细腿数**：上游给的是配对成交笔数，而页面下方明明
    列着单边腿（买入+卖出），两个数字对不上会被当成算错。
    """
    out: dict[str, Any] = {}
    if isinstance(raw, dict):
        out = {k: raw[k] for k, _, _ in SUMMARY_LABELS if k in raw}
    if "final_nav" not in out and equity:
        out["final_nav"] = equity[-1].get("nav")
    fees = [t["fee"] for t in trades if t.get("fee") is not None]
    if fees:
        out.setdefault("total_fee", sum(fees))
    if trades:
        out["n_trades"] = len(trades)
    return {k: v for k, v in out.items() if v is not None}
