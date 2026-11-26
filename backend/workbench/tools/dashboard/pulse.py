"""驾驶舱「今日盘面」块：三大指数卡、涨跌分布与涨跌幅双榜。

**为什么单独一个文件**：``handler.py`` 已在 300 行硬限，盘面块全放这里。

**三大指数**（winmale 口径）：上证 ``index.shzs`` / 深证成指 ``index.szcz``
/ 创业板指 ``index.cyb``。分时 mini 首屏直出（每张 ~1.6k EC，用户拍板；
休市=最近交易日全天分时）。**创业板指的分时上游无覆盖**（同 index.trend
的 cyb 缺口）——该卡无小图，如实。

**兜底假行守卫（2026-11-26 午休实测的坑）**：指数 live 入口对**未知键和
断供键不报错**，而是返回同一份兜底行（cyb/bogus/szzs… 逐位同值、date
停在上一交易日）——cyb 的盘中源间歇性断供时就会拿到它。防线=max-date
规则（见 ``index_cards`` docstring）：**不要用「date==推断 trading_day」
当守卫**——trading_day 来自指数最新日 K（盘后才物化），盘中恒滞后一天，
会反过来把真行滤掉、放行假行（同日 13:07 实测翻车）。
"""

from __future__ import annotations

from typing import Any

from ...tools._shared import as_records, fetch

__all__ = ["PULSE_KEYS", "PULSE_LABELS", "index_cards", "distribution"]

#: 今日盘面的三大指数（winmale 口径；szcz=深证成指，2026-11-26 实测
#: 10102.04 与主站逐位一致）。
PULSE_KEYS: tuple[str, ...] = ("index.shzs", "index.szcz", "index.cyb")

PULSE_LABELS: dict[str, str] = {
    "index.shzs": "上证指数",
    "index.szcz": "深证成指",
    "index.cyb": "创业板指",
}

#: 涨跌双榜条数（winmale 例图为 3，给 5 略宽）。
PULSE_TOP = 5


def index_cards(ctx: Any, warnings: list[str], trading_day: str = "") -> list[dict[str, Any]]:
    """三大指数卡：现价/涨跌/高低 + 分时 mini 序列。

    live_many 1 次请求拿 OHLC（零成本扩字段）；分时每指数 1 次
    （~1.6k EC，首屏直出——用户拍板）。

    两道守卫（都为了「不把假数字画成真行情」，细节见模块 docstring）：
    max-date 过滤更旧的兜底行；``_duplicate_closes`` 过滤**同日**兜底
    （上游把别的指数的整行原样返回）。分时失败的指数只丢小图不告警。
    """
    try:
        raw, _ = fetch(ctx, "kline.query_index_last_live_many", {"keys": list(PULSE_KEYS)})
    except Exception as exc:  # noqa: BLE001 - 指数卡是增补块，失败不拖垮首屏
        warnings.append(f"指数盘中读取失败：{exc}")
        return []
    if not isinstance(raw, dict):
        return []
    rows = _rows(raw)
    if not rows:
        return []
    freshest = max(date for date, _ in rows.values())
    dupes = _duplicate_closes(rows)
    cards: list[dict[str, Any]] = []
    for key in PULSE_KEYS:
        if key not in rows:
            continue
        date, bar = rows[key]
        if date != freshest or key in dupes:
            _note_skipped(warnings, key, same_day=key in dupes)
            continue
        cards.append(_card(ctx, key, date, bar))
    return cards


def _rows(raw: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    """把回包收成 ``key → (日期, 行)``，丢掉没有收盘价的行。"""
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    for key in PULSE_KEYS:
        bar = raw.get(key)
        if isinstance(bar, dict) and bar.get("close") is not None:
            out[key] = (str(bar.get("date") or "")[:10], bar)
    return out


def _note_skipped(warnings: list[str], key: str, *, same_day: bool) -> None:
    """不画这张卡时留下可读原因（页面与日志都能对上）。"""
    if same_day:
        warnings.append(f"指数盘中行疑似兜底（与其他指数同值）：{key}")
    else:
        # 兜底假行/断供：date 比本批最新可得日期旧。不画——把昨天的行
        # 标成今天的指数，比缺一块卡骗得多。
        warnings.append(f"指数盘中行日期偏旧，已跳过：{key}")


def _card(ctx: Any, key: str, date: str, bar: dict[str, Any]) -> dict[str, Any]:
    """单张指数卡（含分时小图）。抽出来是为了 ``index_cards`` 不超函数预算。"""
    return {
        "key": key,
        "label": PULSE_LABELS.get(key, key),
        "close": bar.get("close"),
        "percent": bar.get("percent"),
        "change": bar.get("change"),
        "high": bar.get("high"),
        "low": bar.get("low"),
        "date": date,
        "minute": _minute_series(ctx, key),
    }


def _duplicate_closes(rows: dict[str, tuple[str, dict[str, Any]]]) -> set[str]:
    """找出「收盘价与别的指数完全相同」的键——上游兜底行的同日变体。

    真事（2026-11-26 16:5x 实测）：``index.cyb`` 返回的是 ``index.shzs``
    那一整行（close/amount/volume 逐位相同、source 都是 ``index_quote_eod``），
    而 ``date`` 恰是最新交易日，所以 max-date 守卫放行了它——页面上
    创业板指显示成 3476.88，与上证指数一模一样。

    判断依据：**不同指数的收盘点位不可能同值**。三个及以上同值只保留
    第一个（按 ``PULSE_KEYS`` 顺序，主指数优先），其余判为兜底。
    两个指数同值是可能的巧合（罕见），此时不判——避免误伤真数据。
    """
    seen: dict[float, list[str]] = {}
    for key, (_, bar) in rows.items():
        close = bar.get("close")
        if isinstance(close, (int, float)):
            # 按**页面显示精度**（两位小数）归并：上游兜底行给的是
            # ``3476.8816`` 而上证指数是 ``3476.88``，按四位小数比较会
            # 差一点而漏判——但页面上这两个数就是同一个数。
            seen.setdefault(round(float(close), 2), []).append(key)
    dupes: set[str] = set()
    for keys in seen.values():
        if len(keys) > 1 and len(rows) > 2:
            dupes.update(keys[1:])
    return dupes


def _minute_series(ctx: Any, key: str) -> list[dict[str, Any]]:
    """指数分时 mini 序列（``{t, close}`` 升序）；无覆盖/失败给空。"""
    try:
        raw, _ = fetch(ctx, "kline.query_index_min1_live", {"key": key})
    except Exception:  # noqa: BLE001 - 小图是增补，失败静默丢
        return []
    data = raw if isinstance(raw, dict) else {}
    points = [p for p in (data.get("bars") or []) if isinstance(p, dict)]
    points.sort(key=lambda p: str(p.get("hm") or ""))
    return [{"t": p.get("t"), "close": p.get("close")} for p in points]


def distribution(ctx: Any, warnings: list[str]) -> dict[str, Any]:
    """涨跌分布直方图 + 涨跌幅双榜（行情页同源：bins/movers）。

    bins 是分桶计数（label/count）；双榜各 ``PULSE_TOP`` 条。上游无日期
    字段（宽度族同款），数据日由页头「最新交易日」chip 承担。
    """
    out: dict[str, Any] = {"bins": [], "gainers": [], "losers": []}
    try:
        raw, _ = fetch(
            ctx, "screener.index_breadth_bins", {}, facade=("screener", "index_breadth_bins")
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"涨跌分布读取失败：{exc}")
        return out
    out["bins"] = [
        {
            "label": str(r.get("bin") or r.get("label") or r.get("name") or ""),
            "count": r.get("count"),
        }
        for r in as_records(raw)
        if isinstance(r, dict)
    ]
    for field, desc in (("gainers", True), ("losers", False)):
        try:
            raw, _ = fetch(
                ctx,
                "screener.index_top_movers",
                {"limit": PULSE_TOP, "desc": desc},
                facade=("screener", "index_top_movers"),
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{'涨幅榜' if desc else '跌幅榜'}读取失败：{exc}")
            continue
        out[field] = [
            {"symbol": r.get("symbol"), "name": r.get("name"), "percent": r.get("percent")}
            for r in as_records(raw)
            if isinstance(r, dict)
        ]
    return out
