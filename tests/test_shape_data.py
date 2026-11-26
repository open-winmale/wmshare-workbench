"""形状夹具一致性：``SHAPE_AS_OF`` 必须等于数据里最晚的那一天，且是工作日。

**为什么这条必须有**：这份夹具被百余个 handler 测试当离线数据源。
如果它与数据实际日期不一致，测试会建立在一个**编造的**日期上——
直接违反项目第一条原则「不骗人」。

真实踩过：锚点日曾手写为 ``2026-11-21``（周六），而数据里最晚是
``2026-11-20``（周五）。周六 A 股不可能有数据。手写两份日期必然漂移，
故本文件把这些约束焊住。demo 运行时模式已移除，夹具仅供测试。
"""

from __future__ import annotations

from datetime import date

import pytest
from shape_gen import ANCHOR_DATE, SHAPE_AS_OF, _bar_date, _bars

from datetime import date

import pytest
from shape_gen import ANCHOR_DATE, SHAPE_AS_OF, _bar_date, _bars


class ShapeAsOf:
    def test_is_a_weekday(self):
        """截止日必须是工作日。A 股周末没有数据，页顶不能声称有。"""
        d = date.fromisoformat(SHAPE_AS_OF)
        assert d.weekday() < 5, f"{SHAPE_AS_OF} 是周末，A 股不可能有数据"

    def test_equals_anchor(self):
        """``SHAPE_AS_OF`` 必须由锚点推导，不能另写一份。"""
        assert SHAPE_AS_OF == ANCHOR_DATE.isoformat()

    def test_matches_latest_bar(self):
        """截止日必须等于演示 K 线里最晚的那一天（返回新→旧，[0] 最新）。"""
        latest = _bars("600519")[0]["date"]
        assert latest == SHAPE_AS_OF, (
            f"页顶声称截止 {SHAPE_AS_OF}，但 K 线最晚是 {latest}")

    def test_bars_descending_like_real(self):
        """``kline.query_bars`` 真实返回是**新→旧**（2026-11-25 实测）；
        演示数据必须同向，否则「真实模式一开顺序就翻」又被演示态掩盖。"""
        dates = [b["date"] for b in _bars("600519")]
        assert dates == sorted(dates, reverse=True)

    def test_bar_dates_are_weekdays_only(self):
        """演示 K 线不得落在周末。"""
        for bar in _bars("600519", 40):
            d = date.fromisoformat(bar["date"])
            assert d.weekday() < 5, f"K 线日期 {bar['date']} 是周末"

    def test_bar_dates_strictly_descending(self):
        """``_bar_date(i)`` 随 i 递增而单调变早（否则时间轴会打架）。"""
        dates = [_bar_date(i) for i in range(10)]
        assert dates == sorted(dates, reverse=True)
        assert len(set(dates)) == len(dates)

    def test_snapshots_use_shape_as_of(self):
        """快照的 ``kline_date`` 必须等于截止日（曾硬编码成前一天）。"""
        from shape_gen import _SNAPSHOTS
        for sym, snap in _SNAPSHOTS.items():
            assert snap["kline_date"] == SHAPE_AS_OF, f"{sym} 的 kline_date 不一致"

    def test_fx_and_dividend_dates_use_shape_as_of(self):
        """汇率与分红的日期同样是推导值，不是硬编码。"""
        from shape_data import SHAPE_DATA
        for row in SHAPE_DATA["fx.list"]:
            assert row["date"] == SHAPE_AS_OF
        assert SHAPE_DATA["bonus.snapshot"]["quote_date"] == SHAPE_AS_OF

    @pytest.mark.parametrize("offset", [0, 1, 2, 5, 10, 59])
    def test_bar_date_never_weekend(self, offset: int):
        d = date.fromisoformat(_bar_date(offset))
        assert d.weekday() < 5

    def test_index_valuation_series_are_quarter_end_dates(self):
        """``indices.valuation`` 演示 series 必须与真实同形：``YYYY-MM-DD``
        季度末日期**升序**（曾用 ``2026-Q4`` 期点标签且新→旧，双重失真）。"""
        from shape_gen import _index_valuation
        series = _index_valuation("index.hs300")["series"]
        dates = [p["d"] for p in series]
        assert dates == sorted(dates)
        for d in dates:
            assert len(d) == 10 and d[4] == "-" and d[7] == "-", (
                f"必须是日期，收到 {d!r}")
            assert d[5:7] in ("03", "06", "09", "12"), f"必须是季度末，收到 {d!r}"
        assert series[-1]["d"] <= SHAPE_AS_OF, "演示数据不能晚于截止日"

    def test_screen_result_matches_real_envelope(self):
        """``screener.query`` 真实返回是统一信封（行在 ``data.rows``）——
        旧夹具曾捏成扁平 ``{count, rows}``，handler 读顶层导致真实模式恒空。"""
        from shape_data import SHAPE_DATA
        result = SHAPE_DATA["screener.query"]
        assert result["ok"] is True
        assert isinstance(result["data"], dict)
        assert isinstance(result["data"]["rows"], list) and result["data"]["rows"]
        assert result["data"]["count"] >= len(result["data"]["rows"])

    def test_statement_quarter_shape(self):
        """季报档演示：期次键 ``YYYY-Qn``、最近 5 个已披露季报、降序。"""
        from shape_bind import shape_statement_rows
        rows = shape_statement_rows("statements.income", {"period": "quarter"})
        dates = sorted(rows[0]["vals"], reverse=True)
        assert len(dates) == 5
        assert all("Q" in d for d in dates)
        assert dates[0] == "2026-Q3", "锚点 11-20 的最新已披露季报是 Q3"


class TestSnapshotAndTrendShape:
    """自选换源与驾驶舱换源的两张演示表形状守卫（D-27）。"""

    def test_snapshot_rows_carry_watchlist_columns(self):
        """``kline.snapshot`` 真实是 23 字段（含名称与区间指标）——自选页
        的名称/5日/20日/量比全靠它。旧批量入口 live_many 只有 13 字段，
        曾让这些列在真实模式恒空（演示捏了字段所以全绿）。"""
        from shape_data import SHAPE_DATA
        rows = SHAPE_DATA["kline.snapshot"]
        required = {"name", "chg_5d", "chg_20d", "vol_ratio_5",
                    "kline_date", "close", "percent", "mv"}
        for sym, row in rows.items():
            missing = required - set(row)
            assert not missing, f"{sym} 缺字段 {sorted(missing)}"

    def test_live_many_is_real_13_field_shape(self):
        """live_many 演示必须是真实 13 字段（OHLC/成交 + date），**不得**
        再复用 23 字段快照捏出 name/chg —— 那正是当年四列恒空的根因
        （D-27）；它现在的职责是给自选页伴取行级日期。"""
        from shape_data import SHAPE_DATA
        rows = SHAPE_DATA["kline.query_last_live_many"]
        for sym, row in rows.items():
            assert "date" in row and row["date"], f"{sym} 缺行级日期"
            assert "name" not in row, "live_many 真实无 name 字段"
            assert "chg_5d" not in row and "vol_ratio_5" not in row
            assert {"open", "high", "low", "close", "percent", "volume",
                    "amount", "mv", "sas"} <= set(row)

    def test_index_trend_points_ascending_with_latest(self):
        """``index.trend`` 信封形状：points 升序、末行=最新交易日、
        date/pe/pb 键——驾驶舱取末行当 PE/PB 数据日。"""
        from shape_data import SHAPE_DATA
        for key in ("index.hs300", "index.csi500", "index.sz50"):
            env = SHAPE_DATA["index.trend"][key]
            assert env["ok"] is True
            points = env["data"]["points"]
            dates = [p["date"] for p in points]
            assert dates == sorted(dates), "points 必须升序"
            assert dates[-1] <= SHAPE_AS_OF
            assert {"date", "pe", "pb"} <= set(points[-1])

    def test_index_trend_cyb_empty_like_real(self):
        """真实 ``index.trend`` 不覆盖创业板指（0 行，2026-11-25 实测）——
        演示给空 points 镜像该行为，季度回退路径才能在演示里走通。"""
        from shape_data import SHAPE_DATA
        env = SHAPE_DATA["index.trend"]["index.cyb"]
        assert env["data"]["points"] == []

    def test_index_valuation_cyb_unsupplied_like_real(self):
        """真实 ``indices.valuation`` 对创业板指未供数（pe=null、pb/dv=0，
        2026-11-25 实测）——演示同形。替它编估值会让「这指数没数据」
        看起来像「这指数很便宜」。"""
        from shape_bind import shape_index_valuation
        cur = shape_index_valuation({"key": "index.cyb"})["current"]
        assert cur["pe"] is None and cur["pb"] == 0 and cur["dv"] == 0

    def test_macro_query_is_real_flat_desc_shape(self):
        """真实 ``macro.query`` 是扁平 dict（series 顶层、无 data 信封、
        新→旧、≤10 期）——旧夹具曾捏成信封形+旧→新+12 期，三重失真
        导致真实模式宏观序列块恒「返回结构异常」（D-27）。"""
        from shape_data import SHAPE_DATA
        table = SHAPE_DATA["macro.query"]
        assert "data" not in table, "真实返回没有 data 信封"
        series = table["series"]
        sas = [p["sas"] for p in series]
        assert sas == sorted(sas, reverse=True), "真实 series 是新→旧"
        assert len(series) <= 10, "真实期数上限 10"
        assert {"sas", "value"} <= set(series[0])

    def test_index_trend_shape_fn_narrows_by_key(self):
        """收窄函数：已收录按 key 取，未收录给空 points（不编数据）。"""
        from shape_bind import shape_index_trend
        env = shape_index_trend({"key": "index.hs300"})
        assert env["data"]["key"] == "index.hs300"
        assert env["data"]["points"]
        assert shape_index_trend({"key": "index.others"})["data"]["points"] == []


    def test_min1_live_is_real_flat_shape(self):
        """真实 ``kline.query_min1_live`` 是扁平 dict（bars 顶层升序
        t/close + trading_day/updated_at），~1.6k EC/次——分时分区契约。
        字段口径（2026-11-26 实测）：volume/amount=当日**累计**（非降即错，
        旧演示捏成每分钟值）、*_delta=当分钟增量——均价自算依赖该口径。"""
        from shape_data import SHAPE_DATA
        table = SHAPE_DATA["kline.query_min1_live"]
        for sym, payload in table.items():
            assert {"bar_n", "bars", "market", "symbol",
                    "trading_day", "updated_at"} <= set(payload)
            hm = [b["hm"] for b in payload["bars"]]
            assert hm == sorted(hm), "分时点必须升序"
            first = payload["bars"][0]
            assert {"t", "close", "volume", "amount",
                    "volume_delta"} <= set(first)
            vols = [b["volume"] for b in payload["bars"]]
            assert vols == sorted(vols), "volume 是当日累计，必须非降"
            last = payload["bars"][-1]
            avg = last["amount"] / last["volume"]
            assert last["close"] / 3 <= avg <= last["close"] * 3, \
                "演示的累计口径必须能算出合理均价"
        empty = SHAPE_DATA["kline.query_min1_live"].get("999999")
        assert empty is None or empty["bar_n"] >= 0

    def test_index_live_many_covers_requested_keys(self):
        """指数盘中表按我们请求的键（index.*）出数：close/percent/date
        是驾驶舱瓦片的最小需求；盘面三卡（pulse）还要 high/low。"""
        from shape_data import SHAPE_DATA
        table = SHAPE_DATA["kline.query_index_last_live_many"]
        for key in ("index.hs300", "index.sz50", "index.csi500", "index.cyb",
                    "index.shzs", "index.szcz"):
            row = table[key]
            assert {"close", "percent", "date", "high", "low",
                    "refreshed_at"} <= set(row), key

    def test_last_live_is_real_18_field_shape(self):
        """单票盘中快照必须与 2026-11-26 实测的 18 字段**逐键一致**：
        多捏（如 name/ma*）会让演示冒充档案字段，少捏会让概览合并读空。"""
        from shape_data import SHAPE_DATA
        table = SHAPE_DATA["kline.query_last_live"]
        required = {"symbol", "open", "high", "low", "close", "percent",
                    "change", "amplitude", "volume", "amount", "mv",
                    "mv_free", "turnover_rate", "date", "sas", "asof",
                    "refreshed_at", "source"}
        for sym, row in table.items():
            assert set(row) == required, (
                f"{sym} 字段与实测不一致：多 {set(row) - required}，"
                f"少 {required - set(row)}")
            assert row["date"] == SHAPE_AS_OF
            assert isinstance(row["percent"], float)

    def test_last_live_unknown_symbol_is_none_like_real(self):
        """真实上游对无覆盖标的返回 ``None``（实测 999999）——夹具同形，
        不给兜底假行。"""
        from shape_data import shape_for as demo_for
        assert demo_for("kline.query_last_live", {"sym": "999999"}) is None

    def test_index_min1_live_same_shape_as_stock(self):
        """指数分时与个股分时**同形**（扁平 dict + bars 升序，2026-11-26
        实测）；收录 hs300/shzs/szcz 三键（盘面三卡里 cyb 上游无分时，
        镜像真实缺口），未收录键给 bar_n=0 空载荷。"""
        from shape_data import shape_for as demo_for
        for key in ("index.hs300", "index.shzs", "index.szcz"):
            payload = demo_for("kline.query_index_min1_live", {"key": key})
            assert payload["bar_n"] == len(payload["bars"]) > 0, key
            hm = [b["hm"] for b in payload["bars"]]
            assert hm == sorted(hm), "指数分时点必须升序"
        empty = demo_for("kline.query_index_min1_live", {"key": "index.cyb"})
        assert empty["bar_n"] == 0 and empty["bars"] == []
