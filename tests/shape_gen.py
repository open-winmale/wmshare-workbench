"""形状夹具（测试专用） —— 生成器（各 target 的形状与真实返回同构）。

拆成两个模块的理由：生成器（每类数据的构造）与收窄逻辑（按参数选/变形）
是两个关注点，塞在一个文件里会一路涨过单文件上限。文件名
``shape_gen`` 表示它只产出数据，不决定「哪个 target 用哪份」——
后者在 ``shape_data``。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

#: 形状夹具（测试专用）的**锚点交易日**（周五）。所有演示日期都从它推出，
#: 不手写第二遍——手写两份日期必然漂移（曾经 ``SHAPE_AS_OF`` 写周六、
#: 数据写周五，页顶就声称了一个 A 股不可能有数据的日期）。
ANCHOR_DATE = date(2026, 11, 20)


def _last_trading_day(d: date) -> date:
    """把任意日期回退到最近的工作日（不查真实交易日历，只看周末）。"""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


#: 形状夹具（测试专用）的数据截至日 —— **从锚点推导，不手写**。
#: 页顶的「截止 <日期>」显示的就是它，因此它必须等于数据里最晚的那一天。
SHAPE_AS_OF = ANCHOR_DATE.isoformat()

#: 演示用的几只票（覆盖沪市/深市/创业板/科创板，便于验证代码前缀处理）。
SHAPE_SYMBOLS: tuple[str, ...] = ("600519", "000001", "300750", "688981", "601318")


def _bar_date(i: int) -> str:
    """生成锚点日之前的第 i 个交易日（简化：跳过周末，不查真实日历）。"""
    d = ANCHOR_DATE
    step = 0
    while step < i:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            step += 1
    return d.isoformat()


def _snapshot(symbol: str, name: str, close: float, percent: float,
              industry: str) -> dict[str, Any]:
    """单票行情快照（23 字段，与 ``kline.snapshot`` 完全同形）。"""
    mv = close * 1.25e9
    return {
        "symbol": symbol,
        "name": name,
        "industry": industry,
        "kline_date": SHAPE_AS_OF,
        "kline_sas": "2026:D324",
        "close": close,
        "percent": percent,
        "volume": 6_722_900.0,
        "amount": round(close * 6_722_900.0, 2),
        # 每个标的的区间涨跌必须各不相同：所有行显示同一个数字会让
        # 「这些票走势一致」看起来像数据事实，而那只是形状夹具（测试专用）没做完。
        "chg_5d": round(percent * 1.2 + mv % 7 * 0.0011, 6),
        "chg_10d": round(percent * 1.6 + mv % 5 * 0.0022, 6),
        "chg_20d": round(percent * 2.4 + mv % 11 * 0.0061, 6),
        "chg_90d": round(percent * 3.1 + mv % 13 * 0.0093, 6),
        "roi_1y": round(percent * 3.8 + mv % 17 * 0.0064, 6),
        "ma20": close * 0.958,
        "ma60": close * 0.897,
        "ma120": close * 0.882,
        "vol_ratio_5": 1.5646,
        "mv": mv,
        "mv_free": mv,
        "ma60_up": percent > 0,
        "is_st": False,
        "is_suspend": False,
    }


_SNAPSHOTS: dict[str, dict[str, Any]] = {
    "600519": _snapshot("600519", "贵州茅台", 1485.75, 0.017491, "industry.S34"),
    "000001": _snapshot("000001", "平安银行", 11.86, -0.005013, "industry.S49"),
    "300750": _snapshot("300750", "宁德时代", 268.40, 0.023118, "industry.S63"),
    "688981": _snapshot("688981", "中芯国际", 92.35, 0.009245, "industry.S27"),
    "601318": _snapshot("601318", "中国平安", 58.72, -0.002105, "industry.S49"),
}


def _live_many_row(symbol: str) -> dict[str, Any]:
    """``kline.query_last_live_many`` 行（**13 字段，与真实逐键一致**）。

    旧演示复用 23 字段快照，多捏了 name/chg_*/ma*/vol_ratio_5——真实
    只有 OHLC/成交与日期，自选页那四列曾因此在真实模式恒空（D-27）。
    现在自选列走 snapshot 批量，此接口只作**日期伴取**（快照批量路由
    不物化 kline_date），``date`` 是它的存在理由。
    """
    snap = _SNAPSHOTS[symbol]
    return {
        "symbol": symbol,
        "open": round(snap["close"] * (1 - snap["percent"]), 2),
        "high": round(snap["close"] * 1.008, 2),
        "low": round(snap["close"] * 0.992, 2),
        "close": snap["close"],
        "percent": snap["percent"],
        "volume": snap["volume"],
        "amount": snap["amount"],
        "mv": snap["mv"],
        "mv_free": snap["mv"],
        "date": SHAPE_AS_OF,
        "sas": "2026:D329",
        "asof": "",
        "refreshed_at": "",
    }


def _live_row(symbol: str) -> dict[str, Any]:
    """``kline.query_last_live`` 单票盘中快照（**18 字段，2026-11-26
    实测逐键一致**：OHLC/成交/市值/振幅/换手 + ``date/asof/refreshed_at/
    sas/source``；``percent`` 是小数）。概览页用它把「上一收盘」提到
    盘中现价。演示锚点只有一天，``date`` 与快照 ``kline_date`` 同日
    ——合并走「严格新于才覆盖」，演示里不触发（覆盖路径由单测钉）。"""
    snap = _SNAPSHOTS[symbol]
    return {
        "symbol": symbol,
        "open": round(snap["close"] * (1 - snap["percent"]), 2),
        "high": round(snap["close"] * 1.008, 2),
        "low": round(snap["close"] * 0.992, 2),
        "close": snap["close"],
        "percent": snap["percent"],
        "change": round(snap["close"] * snap["percent"], 2),
        "amplitude": 0.016,
        "volume": snap["volume"],
        "amount": snap["amount"],
        "mv": snap["mv"],
        "mv_free": snap["mv"],
        "turnover_rate": 0.11,
        "date": SHAPE_AS_OF,
        "sas": "2026:D329",
        "asof": f"{SHAPE_AS_OF} 10:30:00",
        "refreshed_at": f"{SHAPE_AS_OF} 10:30:05",
        "source": "tencent",
    }


def _bars(symbol: str, n: int = 60) -> list[dict[str, Any]]:
    """日 K 序列（date **降序=新→旧**，字段与顺序都跟 ``kline.query_bars``
    的真实返回一致——2026-11-25 实测真实返回是新→旧，形状夹具（测试专用）曾是旧→新，
    正是「演示按前端方便捏」的反面教材）。"""
    base = float(_SNAPSHOTS.get(symbol, {}).get("close") or 100.0)
    out: list[dict[str, Any]] = []
    # 从当前价往回推，制造一段有起伏的历史（确定性，不用随机）
    for i in range(n):
        j = n - 1 - i  # j=0 是最旧一天（走势公式按旧序不变）
        drift = 1.0 + (j / n) * 0.16 + ((j % 7) - 3) * 0.004
        close = base * drift
        open_ = close * 0.995
        out.append({
            "date": _bar_date(i),
            "open": round(open_, 2),
            "high": round(max(open_, close) * 1.008, 2),
            "low": round(min(open_, close) * 0.992, 2),
            "close": round(close, 2),
            "volume": 5_000_000.0 + (j % 11) * 180_000.0,
            "amount": round(close * (5_000_000.0 + (j % 11) * 180_000.0), 2),
            "percent": round((close / (open_ or 1.0)) - 1.0, 6),
            "sas": f"2026:D{324 - i}",
        })
    return out


#: 各指数的估值差异（演示）。**每只指数必须不同**——四个指数显示完全相同的
#: PE/PB 会让「指数间没有差异」看起来像数据事实，用户会据此做出错误判断。
_INDEX_PROFILE: dict[str, dict[str, float]] = {
    "index.hs300": {"pe": 13.42, "pb": 1.47, "dv": 0.0218},
    "index.csi500": {"pe": 27.85, "pb": 2.13, "dv": 0.0135},
    "index.sz50": {"pe": 11.06, "pb": 1.22, "dv": 0.0287},
    "index.cyb": {"pe": 41.20, "pb": 4.38, "dv": 0.0062},
    "index.zz500": {"pe": 24.63, "pb": 1.94, "dv": 0.0148},
}


def _quarter_ends(count: int) -> list[str]:
    """截至锚点的最近 ``count`` 个**季度末日期**（升序）。

    与真实 ``index.valuation`` 的 ``series[].d`` 同形——samples 实证是
    ``YYYY-MM-DD``（如 2025-12-31）升序；演示曾用 ``2026-Q4`` 这类期点
    标签且新→旧，格式与方向双重失真（D-27）。
    """
    year, month = ANCHOR_DATE.year, ((ANCHOR_DATE.month - 1) // 3) * 3 + 3
    if date(year, month, _last_day(year, month)) > ANCHOR_DATE:
        # 锚点所在季度的季度末还没到（如 11-20 锚点 → 12-31）：回退一季
        year, month = _shift_quarter(year, month)
    ends: list[str] = []
    for _ in range(count):
        ends.append(f"{year:04d}-{month:02d}-{_last_day(year, month):02d}")
        year, month = _shift_quarter(year, month)
    ends.reverse()
    return ends


def _shift_quarter(year: int, month: int) -> tuple[int, int]:
    """季度末 (year, month) 往前推一季。"""
    month -= 3
    return (year - 1, month + 12) if month <= 0 else (year, month)


def _last_day(year: int, month: int) -> int:
    """季度末月的最后一天（3/6/9/12 月 → 31/30/30/31）。"""
    return {3: 31, 6: 30, 9: 30, 12: 31}[month]


def _index_valuation(key: str) -> dict[str, Any]:
    """指数估值（``indices.valuation`` 形状：current + 季频 series，**日期
    升序**，与 samples 一致）。

    创业板指与真实一致**未供数**（pe=null、pb/dv=0，2026-11-25 实测）：
    演示同形，handler 的 0 值归一与缺失告警路径才能在演示里走通——
    替它编估值会让「这指数没数据」看起来像「这指数很便宜」。
    """
    quarters = _quarter_ends(8)
    n = len(quarters)
    if key == "index.cyb":
        return {
            "current": {"pe": None, "pb": 0, "dv": 0},
            "series": [{"d": d, "pe": None, "pb": 0} for d in quarters],
        }
    base = _INDEX_PROFILE.get(key, {"pe": 20.0, "pb": 2.0, "dv": 0.015})
    return {
        "current": dict(base),
        "series": [
            {"d": d,
             "pe": round(base["pe"] * (1 - (n - 1 - i) * 0.011), 4),
             "pb": round(base["pb"] * (1 - (n - 1 - i) * 0.008), 4)}
            for i, d in enumerate(quarters)
        ],
    }


def _index_trend(key: str) -> dict[str, Any]:
    """指数周频估值（``cli.index.trend`` **统一信封**形状：``data.points``
    升序、末行=最新交易日，date/pe/pb 键）。

    创业板指与真实一致给**空 points**——该源不覆盖它（2026-11-25 实测
    0 行），驾驶舱的季度回退路径必须在演示里走得通，不能替它编数据。
    """
    if key == "index.cyb":
        points: list[dict[str, Any]] = []
    else:
        base = _INDEX_PROFILE.get(key, {"pe": 20.0, "pb": 2.0, "dv": 0.015})
        # 周采样：每 7 天一个点，升序，末行恰为锚点日（最新交易日）
        offsets = (42, 35, 28, 21, 14, 7, 0)
        n = len(offsets)
        points = [
            {"date": _bar_date(off),
             "pe": round(base["pe"] * (1 + (i - n + 1) * 0.009), 4),
             "pb": round(base["pb"] * (1 + (i - n + 1) * 0.006), 4)}
            for i, off in enumerate(offsets)
        ]
    return {"ok": True, "as_of": SHAPE_AS_OF,
            "data": {"key": key, "points": points}, "meta": {}}


_EQUITY_CURVE: list[dict[str, Any]] = [
    {"date": _bar_date(59 - i), "nav": round(1_000_000.0 * (1 + i * 0.0028), 2)}
    for i in range(60)
]

_TRADES: list[dict[str, Any]] = [
    {"date": _bar_date(52), "side": "buy", "price": 1288.4, "shares": 100,
     "amount": 128840.0, "fee": 38.65, "reason": "MA5 上穿 MA20"},
    {"date": _bar_date(31), "side": "sell", "price": 1402.6, "shares": 100,
     "amount": 140260.0, "fee": 70.13, "reason": "MA5 下穿 MA20",
     "pnl": 11347.22, "ret": 0.08806, "hold_days": 21},
    {"date": _bar_date(18), "side": "buy", "price": 1435.2, "shares": 100,
     "amount": 143520.0, "fee": 43.06, "reason": "MA5 上穿 MA20"},
]


def _live_tables() -> dict[str, Any]:
    """行情族演示表（K 线/快照/分时/指数盘中）。"""
    tables = {
        # 自选/持仓批量快照 = kline.snapshot（23 字段）；live_many 只作
        # 自选页日期伴取（快照批量路由不物化 kline_date）
        "kline.snapshot": {s: _SNAPSHOTS[s] for s in _SNAPSHOTS},
        "kline.query_last_live_many": {s: _live_many_row(s)
                                       for s in _SNAPSHOTS},
        "kline.query_last_live": {s: _live_row(s) for s in _SNAPSHOTS},
        "kline.query_bars": {s: _bars(s) for s in _SNAPSHOTS},
        "kline.query_bars_adj": {s: _bars(s) for s in _SNAPSHOTS},
        # cli.kline.bars 门面（回测页价格图 + 驾驶舱/行情页交易日推断用）。
        # 真实返回是 DataFrame，演示给 list——两条路径都过 normalize_bars
        # 归一（交易日推断只取 max date），形状差异不外泄。
        "kline.bars": {s: _bars(s) for s in _SNAPSHOTS},
        # 驾驶舱 PE/PB 的最新交易日口径（信封形状见 _index_trend）
        "index.trend": {k: _index_trend(k) for k in _INDEX_PROFILE},
        # 个股分时（shape_min1_live 按 sym 收窄）
        "kline.query_min1_live": {
            s: {"bar_n": len(_min1_bars(s)), "bars": _min1_bars(s),
                "market": "cn", "symbol": s,
                "trading_day": SHAPE_AS_OF,
                "updated_at": f"{SHAPE_AS_OF} 10:30:00"}
            for s in _SNAPSHOTS},
    }
    tables.update(_index_live_tables())
    return tables


def _index_live_tables() -> dict[str, Any]:
    """指数盘中演示表：分时（同个股分时形状）与 live 批量。"""
    return {
        # 指数分时（index. 前缀显式路由；与个股分时同形，实测 bars 多
        # amount_delta/volume_delta 两个增量字段——演示不给，归一本来
        # 就只读 t/hm/close）
        "kline.query_index_min1_live": {
            k: {"bar_n": len(_min1_bars(k, base)),
                "bars": _min1_bars(k, base),
                "market": "cn", "symbol": k,
                "trading_day": SHAPE_AS_OF,
                "updated_at": f"{SHAPE_AS_OF} 10:30:00"}
            # 盘面三大指数里 cyb 上游无分时（镜像真实缺口，卡上无小图）
            for k, base in (("index.hs300", 3916.41),
                            ("index.shzs", 3475.36),
                            ("index.szcz", 10102.04))},
        "kline.query_index_last_live_many": {
            **{k: {"date": SHAPE_AS_OF, "close": round(4000.0 + i * 300.0, 2),
                   "percent": round(-0.002 + i * 0.001, 4),
                   "change": round(-8.0 + i * 4.0, 2),
                   "open": 4010.0 + i * 300.0, "high": 4020.0 + i * 300.0,
                   "low": 3995.0 + i * 300.0,
                   "asof": f"{SHAPE_AS_OF} 10:30:00",
                   "refreshed_at": f"{SHAPE_AS_OF} 10:30:05",
                   "source": "tencent_index"}
               for i, k in enumerate(_INDEX_PROFILE)},
            # 盘面三卡（pulse.PULSE_KEYS）：shzs/szcz 数值镜像 2026-11-26
            # 盘中实测；cyb=上游 live 源间歇断供（实施数值给真量级，date
            # =SHAPE_AS_OF 时守卫放行——断供形态由单测钉）
            "index.shzs": {"date": SHAPE_AS_OF, "close": 3475.36,
                           "percent": -0.0003, "change": -1.11,
                           "open": 3492.1, "high": 3497.81, "low": 3469.65,
                           "asof": f"{SHAPE_AS_OF} 11:29:48",
                           "refreshed_at": f"{SHAPE_AS_OF} 11:29:52",
                           "source": "tencent_index"},
            "index.szcz": {"date": SHAPE_AS_OF, "close": 10102.04,
                           "percent": 0.0016, "change": 15.68,
                           "open": 10120.4, "high": 10235.5, "low": 10094.17,
                           "asof": f"{SHAPE_AS_OF} 11:29:48",
                           "refreshed_at": f"{SHAPE_AS_OF} 11:29:52",
                           "source": "tencent_index"},
            "index.cyb": {"date": SHAPE_AS_OF, "close": 2207.5,
                          "percent": 0.011, "change": 23.92,
                          "open": 2190.0, "high": 2227.41, "low": 2181.37,
                          "asof": f"{SHAPE_AS_OF} 11:29:48",
                          "refreshed_at": f"{SHAPE_AS_OF} 11:29:52",
                          "source": "tencent_index"},
        },
    }


def _market_payload() -> dict[str, Any]:
    """行情与全市场宽度。"""
    return {
        **_live_tables(),

        # ---- 全市场宽度 / 涨跌榜 ----
        "screener.index_breadth_summary": {
            "up": 2861, "down": 1932, "flat": 291,
            "limit_up": 62, "limit_down": 9,
            "up_pct": 0.5622, "down_pct": 0.3795, "flat_pct": 0.0572,
            "pct_of_total": 0.9990, "median_pct": 0.0031,
        },
        "screener.index_top_movers": [
            {"symbol": s, "name": d["name"], "percent": d["percent"]}
            for s, d in sorted(_SNAPSHOTS.items(),
                               key=lambda kv: -abs(kv[1]["percent"]))
        ],
        "screener.index_breadth_bins": [
            {"bin": "跌停", "count": 9},
            {"bin": "< -7%", "count": 34},
            {"bin": "-7% ~ -3%", "count": 268},
            {"bin": "-3% ~ 0", "count": 1621},
            {"bin": "0", "count": 291},
            {"bin": "0 ~ 3%", "count": 2288},
            {"bin": "3% ~ 7%", "count": 411},
            {"bin": "> 7%", "count": 162},
            {"bin": "涨停", "count": 62},
        ],
        "screener.index_breadth_bin_industries": [
            {"bin": "0 ~ 3%", "industry": "industry.S34", "count": 42},
            {"bin": "> 7%", "industry": "industry.S27", "count": 11},
        ],
        # ---- 指数 ----
        "indices.keys": ["index.hs300", "index.csi500", "index.sz50", "index.cyb"],
        "indices.universe_keys": ["index.hs300", "index.csi500", "index.sz50",
                                  "index.cyb", "index.zz500"],
        # ---- 资金流 ----
        "moneyflow.board": [
            {"symbol": s, "name": d["name"], "industry": d["industry"],
             "net_mf": 1_859_609_500.0 / (i + 1),
             "elg_net": -195_192_800.0 / (i + 1),
             "lg_net": 287_699_300.0 / (i + 1),
             "md_net": -262_199_700.0 / (i + 1),
             "sm_net": 169_693_200.0 / (i + 1),
             "net_mv_ratio": 0.001764 / (i + 1)}
            for i, (s, d) in enumerate(sorted(_SNAPSHOTS.items()))
        ],
    }


def _min1_bars(symbol: str, base: float | None = None) -> list[dict[str, Any]]:
    """当日 1 分钟分时（与真实 ``kline.query_min1_live`` 同形同向：
    bars **升序** ``{t, hm, close, volume, amount, volume_delta,
    amount_delta, n, source}``——**volume/amount=当日累计**（volume 为
    股）、``*_delta``=当分钟增量，2026-11-26 实测口径（旧演示捏成
    「每分钟递增」的累计值没有、delta 缺失，均价自算会在演示里算错）；
    trading_day/updated_at 顶层）。真实盘中首查 ~1.6k EC，点数随交易
    时间增长——演示给上午段 60 点（锚点日内）。指数键（指数分时与个股
    同形，2026-11-26 实测）不在 ``_SNAPSHOTS``，base 显式传。"""
    base = float(base if base is not None
                 else _SNAPSHOTS.get(symbol, {}).get("close") or 100.0)
    out: list[dict[str, Any]] = []
    vol_cum = 0.0
    amt_cum = 0.0
    for i in range(60):
        hm = f"{(9 * 60 + 30 + i) // 60:02d}{(9 * 60 + 30 + i) % 60:02d}"
        t = f"{hm[:2]}:{hm[2:]}"
        price = round(base * (1 + ((i % 7) - 3) * 0.0008), 2)
        d_vol = 100000.0 + i * 8000.0
        d_amt = round(price * d_vol, 2)
        vol_cum += d_vol
        amt_cum += d_amt
        out.append({"t": t, "hm": hm, "close": price,
                    "volume": vol_cum, "amount": amt_cum,
                    "volume_delta": d_vol, "amount_delta": d_amt,
                    "n": 3 + i % 5, "source": "tencent"})
    return out


def _macro_series() -> list[dict[str, Any]]:
    """$CPI 演示序列（**新→旧**，与真实 ``macro.query`` 同向同形）。

    真实返回是扁平 dict（series 顶层、无 data 信封）、点为新→旧、
    期数上限 10（2026-11-26 实测）。demo 曾捏成信封形+旧→新+12 期，
    三重失真导致真实模式序列块恒「返回结构异常」（D-27）。
    """
    out: list[dict[str, Any]] = []
    year, month = 2026, 10
    for i in range(10):
        out.append({"annual": year, "sampling": f"M{month:02d}",
                    "sas": f"{year}:M{month:02d}",
                    "value": round(100.7 - i * 0.11, 2)})
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return out


def _macro_payload() -> dict[str, Any]:
    """宏观、汇率、目录、日历。"""
    return {
        "macro.query": {
            "ok": True, "frequency": "month", "periods": 10,
            "metric": "$CPI", "store": "cpi",
            "latest": {"annual": 2026, "sampling": "M10",
                       "sas": "2026:M10", "value": 100.7},
            "series": _macro_series(),
        },
        "macro.bond_curve": {"curve_name": "中债国债收益率曲线", "tenor": "10年",
                             "value": 0.0168},
        "macro.spots": [
            {"sas": f"2026:M{m:02d}", "value": 100.0 + m * 0.1}
            for m in range(1, 13)
        ],
        "fx.list": [
            {"ccy": "USD", "date": SHAPE_AS_OF, "middle": 7.1023},
            {"ccy": "EUR", "date": SHAPE_AS_OF, "middle": 7.7412},
            {"ccy": "JPY", "date": SHAPE_AS_OF, "middle": 0.04712},
            {"ccy": "HKD", "date": SHAPE_AS_OF, "middle": 0.91234},
        ],
        "fx.rate": {"ccy": "USD", "date": SHAPE_AS_OF, "middle": 7.1023,
                    "buy": 7.0918, "cash_buy": 7.0432, "currency": "美元"},
        "stocks.query_list": [
            {"symbol": s, "name": d["name"], "industry": d["industry"],
             "is_st": False, "list_date": "2001-08-27"}
            for s, d in sorted(_SNAPSHOTS.items())
        ],
        "calendar.days": [_bar_date(i) for i in range(10)],
        "board.concept_list": [
            {"concept": "白酒", "count": 42},
            {"concept": "新能源车", "count": 186},
            {"concept": "半导体", "count": 213},
        ],
    }


def _fundamental_payload() -> dict[str, Any]:
    """估值、分红、报表、回测。"""
    return {
        "valuation.daily_basic": _daily_basic(),
        # 分红快照：形状同真实 bonus.snapshot（18 字段的 dict）。
        # 注意 bonus.snapshot_yield_ttm 返回的是**裸 float**，不是 dict——
        # 按 dict 处理会静默得到 {}，页面显示「—」而数据其实可用。
        "bonus.snapshot": _dividend_snapshot(),
        "bonus.query_list": _dividend_history(),
        # 三表与指标全部走 statements 门面（period 由 shape_bind 变形）。
        # 形状同真实：list[{cn, k, vals{期次: 值}}]，跨期列。
        # 演示态曾捏成 {data:{items:[{key,label,value,yoy}]}}，与真实完全不同——
        # 那种「演示能跑、真机就崩」的形状偏差正是本项目反复修的那类错。
        "statements.income": _statement_rows(),
        "statements.balance": _statement_rows(),
        "statements.cashflow": _statement_rows(),
        # 主要指标：走门面 statements.indicators。形状同真实：
        # list[{k, cn, vals{期次: 值}}]，49 项。
        "statements.indicators": _indicator_rows(),
        "rptdom.statement_tree": {
            "ok": True, "as_of": "2026-09-30",
            "data": {"symbol": "600519", "domain": "income",
                     "tree": [{"key": "total_revenue", "label": "营业总收入",
                               "value": 1.234e11,
                               "children": [{"key": "operating_revenue",
                                             "label": "营业收入",
                                             "value": 1.231e11}]}]},
            "meta": {},
        },
        "backtest.run": {
            "trades": _TRADES,
            # 键名与上游真实 summary **一致**（2026-11-26 实测）：上游给
            # cagr / n_trades / avg_hold_days / buy_hold_return，不返回
            # final_nav / total_fee（由 handler 从净值末点与 fee 求和现算）。
            # 夹具此前捏 annual_return / trades / final_nav / total_fee，
            # 于是「四项恒为 —」的真实缺陷在离线测试里永远看不见。
            "summary": {
                "total_return": 0.3821, "cagr": 0.2143,
                "max_drawdown": -0.1284, "sharpe": 1.31,
                "win_rate": 0.6667, "n_trades": 3,
                "avg_hold_days": 12.5, "buy_hold_return": 0.2013,
            },
            "equity": _EQUITY_CURVE,
            "caliber": {
                "commission": 0.0003, "min_fee": 5.0, "stamp_duty": 0.0005,
                "lot_size": 100, "fill": "next_open", "settle": "T+1",
                "adj": "qfq", "skipped": 0,
            },
        },
        "screener.query": _screen_result(),
    }


def _indicator_rows() -> list[dict[str, Any]]:
    """主要财务指标（演示）—— 与真实 ``statements.indicators`` 同构。"""
    years = ("2025", "2024", "2023", "2022", "2021")
    base: tuple[tuple[str, float, float], ...] = (
        # (key, 最新值, 每年衰减率)
        ("totalOperatingIncome", 1.7205e11, 0.07),
        ("deduParentProfit", 8.2293e10, 0.06),
        ("roe", 0.3253, 0.012),
        ("grossProfitRatio", 0.9118, 0.004),
        ("netProfitRatio", 0.5053, 0.008),
        ("basicEps", 65.66, 0.06),
        ("dilutedEps", 65.66, 0.06),
        ("equityRatio", 0.1964, 0.02),
        ("totalAssetTr", 0.005709, 0.01),
        ("inventoryTr", 0.002573, 0.01),
        ("xjllb", 1.2401, 0.06),
        ("totalAssetTdays", 630.62, 0.01),
    )
    rows: list[dict[str, Any]] = []
    for key, latest, decay in base:
        vals = {y: round(latest * (1 - decay) ** i, 6)
                for i, y in enumerate(years)}
        rows.append({"k": key, "cn": key, "vals": vals})
    return rows


def _dividend_snapshot() -> dict[str, Any]:
    """分红快照（演示）—— 字段与真实 ``bonus.snapshot`` 对齐。"""
    return {
        "symbol": "600519", "name": "贵州茅台", "industry": "industry.S34",
        "quote_date": SHAPE_AS_OF,
        "yield_ttm": 0.035458, "payout_ttm": 0.791536, "dps_ttm": 51.98123,
        "yield_lyr": 0.035442, "yield_3y_avg": 0.043708,
        "yield_3y_min": 0.038377, "yield_3y_trend": "valley",
        "bonus_3y_trend": "valley", "bonus_npts_rate": 0.591083,
        "bonus_total": 4.0114e11, "bonus_ttm": 6.5033e10,
        "pe_ttm": 22.3155, "mv": 1.8335e12, "is_suspend": False,
        "pct_yield_3y": 0.44906,
    }


def _dividend_history() -> list[dict[str, Any]]:
    """逐次派息（演示）—— 字段与真实 ``bonus.query_list`` 对齐。"""
    return [
        {"announce": "2026-06-22", "ex_div": "2026-06-25",
         "record_date": "2026-06-25", "sas": "2025:Q4",
         "dps": 27.67, "payout_ratio": 0.752, "ccy": "CNY"},
        {"announce": "2025-11-06", "ex_div": "2025-12-18",
         "record_date": "2025-12-18", "sas": "2025:Q3",
         "dps": 23.88, "payout_ratio": 0.801, "ccy": "CNY"},
        {"announce": "2025-06-20", "ex_div": "2025-06-26",
         "record_date": "2025-06-26", "sas": "2024:Q4",
         "dps": 23.88, "payout_ratio": 0.786, "ccy": "CNY"},
    ]


def _statement_rows() -> list[dict[str, Any]]:
    """三表科目（演示）—— 每年一行一个科目、各期一列，与真实返回同构。"""
    years = ("2025", "2024", "2023")
    base = [
        ("total_revenue", "营业收入", 1.688e11),
        ("total_operating_cost", "营业总成本", 5.737e10),
        ("operating_cost", "营业成本", 1.329e10),
        ("operating_profit", "营业利润", 1.14e11),
        ("total_profit", "利润总额", 1.142e11),
        ("net_profit", "净利润", 8.62e10),
        ("net_profit_attr_p", "归母净利润", 8.62e10),
    ]
    out: list[dict[str, Any]] = []
    for i, (key, cn, latest) in enumerate(base):
        vals = {y: round(latest * (1 - 0.06 * j), 2)
                for j, y in enumerate(years)}
        out.append({"k": key, "cn": cn, "vals": vals})
    return out


def _screen_result() -> dict[str, Any]:
    """条件选股结果——**真实形状是统一信封**：行在 ``data.rows``、命中数在
    ``data.count``（且真实 ``data.rows`` 是 DataFrame，handler 过 as_records）。

    此前 demo 捏成扁平 ``{count, rows}``，与真实不同形——handler 读顶层
    `rows` 在演示态全绿、真实模式恒空，「选股选不到」的根因（D-25/D-27）。
    行里的键是**指标码**（``$`` 前缀），前端按行键动态生成列。
    """
    return {
        "ok": True,
        "as_of": SHAPE_AS_OF,
        "data": {
            "count": 5,
            "rows": [
                {"symbol": s, "name": d["name"],
                 "$PE_TTM": round(11.0 + i * 3.4, 2),
                 "$PB": round(0.92 + i * 0.28, 2),
                 "$ABOVE_MA20": 1 if d["percent"] > 0 else 0}
                for i, (s, d) in enumerate(sorted(_SNAPSHOTS.items()))
            ],
        },
    }


def _daily_basic() -> dict[str, Any]:
    """估值长表（``valuation.daily_basic`` 真实形状：每行一个字段值）。"""
    return {
        "ok": True, "as_of": SHAPE_AS_OF,
        "data": [
            {"date": _bar_date(i), "field": f, "symbol": "600519", "value": v}
            for i in range(30)
            for f, v in (("pe_ttm", 20.17 + i * 0.05), ("pb", 7.42 + i * 0.01),
                         ("ps", 9.98), ("pr", 0.535), ("total_mv", 1.857e12),
                         ("circ_mv", 1.857e12))
        ],
        "meta": {"count": 180, "db": "alt.valuation_daily",
                 "fields": ["pe_ttm", "pb", "ps", "pr", "total_mv", "circ_mv"],
                 "requested_unknown": [],
                 "window": {"requested_begin": "2026-01-01",
                            "truncated": False}},
    }

