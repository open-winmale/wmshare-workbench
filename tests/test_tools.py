"""九个工具 handler 的离线测试。

**这些用例抓的是「不变量」，不是「能不能跑」**。每个工具都有一条
「做错了也照样显示出漂亮表格」的路径，所以断言都落在那种地方：

- 自选：批量请求数必须恰为 1（逐票也能出同样的表，但花 N 倍钱）
- 驾驶舱：不得发出任何 Manual 级调用（首屏每开一次都花钱）
- 选股：重列超预算时**零请求**
- 个股：高成本分区默认请求时**零请求**
- 账本：五法结果必须互不相同；缺价不计入合计
- 凭证：探针失败不替换、secret 不回显

全部离线零网络：``FakeFetcher`` 挂 ``tests/shape_*`` 形状夹具。
"""

from __future__ import annotations

import json
import pathlib

import pytest
from shape_data import shape_for
from workbench.bootstrap import build_context
from workbench.client.fetchers import FakeFetcher
from workbench.platform.store import Store


@pytest.fixture()
def ctx(tmp_path: pathlib.Path):
    """形状夹具上下文（零凭证零网络）。"""
    return build_context(fetcher=FakeFetcher(resolver=shape_for),
                         store=Store(tmp_path / "t.db"))


def run(ctx, slug: str, params: dict | None = None) -> dict:
    return ctx.registry[slug](ctx, params or {})


def envelope_ok(env: dict) -> None:
    """所有信封共同的结构约束。"""
    assert set(env) == {"ok", "as_of", "data", "meta", "freshness",
                        "warnings", "ec"}, f"信封字段异常：{sorted(env)}"
    assert env["freshness"] in ("fresh", "stale", "expired", "unknown")


# --------------------------------------------------------------------------
# 自选
# --------------------------------------------------------------------------

class TestWatchlist:
    def test_single_batch_request(self, ctx):
        """**核心验收**：无论多少标的，上游只被调用两次（快照 + 日期伴取）。

        逐票循环也能渲染出完全一样的表格，但那一页有 20 只票就会打 40 次
        请求——而用户看不出差别。列走 ``kline.snapshot``（sym 传列表自动
        路由批量，23 字段含名称与区间指标），日期伴取 live_many（快照
        批量路由不物化 kline_date，合同原文）。
        """
        before = len(ctx.fetcher.calls)
        env = run(ctx, "watchlist", {"symbols": "600519,000001,300750,688981"})
        envelope_ok(env)
        assert env["ok"] is True
        new_calls = ctx.fetcher.calls[before:]
        assert len(new_calls) == 2, f"应只发 2 次请求，实际 {len(new_calls)}"
        assert new_calls[0][0] == "kline.snapshot"
        assert new_calls[0][1].get("sym") == ["600519", "000001",
                                              "300750", "688981"]
        assert new_calls[1][0] == "kline.query_last_live_many"
        assert env["data"]["request_count"] == 2

    def test_batch_dates_merged_from_live_many(self, ctx):
        """快照批量路由不物化 kline_date（真实返回 None）——行级截止日从
        live_many 的 ``date`` 伴取合并；信封 as_of = 各行 max。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "600519": {"symbol": "600519", "name": "贵州茅台",
                       "close": 1460.0, "percent": 0.01, "kline_date": None},
            "000001": {"symbol": "000001", "name": "平安银行",
                       "close": 11.8, "percent": -0.005, "kline_date": None},
        }
        env = run(ctx, "watchlist", {"symbols": "600519,000001"})
        dates = {r["symbol"]: r["kline_date"] for r in env["data"]["rows"]}
        assert dates == {"600519": "2026-11-20", "000001": "2026-11-20"}
        assert env["as_of"] == "2026-11-20"
        assert env["warnings"] == [], "日期伴取成功不应有告警"

    def test_batch_dates_failure_degrades_to_unknown(self, ctx):
        """伴取失败只丢页级日期（告警 + 截至未知），**不丢任何行情列**——
        为了日期让整页失败是把代价倒挂。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "600519": {"symbol": "600519", "name": "贵州茅台",
                       "close": 1460.0, "percent": 0.01, "kline_date": None},
        }

        original = ctx.fetcher.call

        def no_dates(target, **params):
            if target == "kline.query_last_live_many":
                raise RuntimeError("boom")
            return original(target, **params)

        ctx.fetcher.call = no_dates
        env = run(ctx, "watchlist", {"symbols": "600519"})
        row = env["data"]["rows"][0]
        assert row["close"] == 1460.0 and row["name"] == "贵州茅台"
        assert not row["kline_date"]
        assert any("截至未知" in w for w in env["warnings"])

    def test_rows_carry_name_and_window_metrics(self, ctx):
        """名称与 5日/20日/量比必须随批量快照一次返回。

        旧入口 ``kline.query_last_live_many`` 真实每票只有 13 字段，这三列
        加名称在真实模式下恒空（演示捏了字段所以全绿，D-27）。换
        ``kline.snapshot`` 后这些字段是返回的一部分，这里焊住。
        """
        env = run(ctx, "watchlist", {"symbols": "600519,000001"})
        for row in env["data"]["rows"]:
            assert row["name"] and row["name"] != row["symbol"], \
                "名称不得回落成代码"
            assert row["chg_5d"] is not None
            assert row["chg_20d"] is not None
            assert row["vol_ratio_5"] is not None

    def test_batchresult_wrapper_still_extracts_rows(self, ctx):
        """真实批量返回是 ``BatchResult``（快照表在 ``.results``）——
        ``isinstance(raw, dict)`` 会把它整个判空（持仓页 D-25 同款）。"""
        class FakeBatchResult:
            results = {
                "600519": {"symbol": "600519", "name": "贵州茅台",
                           "close": 1460.0, "percent": 0.01,
                           "chg_5d": 0.03, "chg_20d": 0.05,
                           "vol_ratio_5": 1.2, "amount": 1.0, "mv": 2.0,
                           "kline_date": "2026-11-25"},
            }

        ctx.fetcher._override["kline.snapshot"] = FakeBatchResult()
        env = run(ctx, "watchlist", {"symbols": "600519"})
        row = env["data"]["rows"][0]
        assert row["name"] == "贵州茅台"
        assert row["close"] == 1460.0

    def test_nameless_row_shows_dash_not_code(self, ctx):
        """快照缺名称时显示「—」——**拿代码冒充名称**会让用户以为是真名
        （换源前真实模式就是这么显示的）。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "600519": {"symbol": "600519", "close": 1460.0,
                       "percent": 0.01, "kline_date": "2026-11-25"},
        }
        env = run(ctx, "watchlist", {"symbols": "600519"})
        assert env["data"]["rows"][0]["name"] == "—"

    def test_rows_follow_request_order(self, ctx):
        """返回行顺序必须与请求顺序一致（服务端 MAP 无序）。"""
        symbols = ["300750", "600519", "000001"]
        env = run(ctx, "watchlist", {"symbols": ",".join(symbols)})
        got = [r["symbol"] for r in env["data"]["rows"]]
        assert got == symbols

    def test_missing_symbol_kept_as_row(self, ctx):
        """无数据的标的不从表里消失——保留一行并标 missing。"""
        env = run(ctx, "watchlist", {"symbols": "600519,999999"})
        rows = {r["symbol"]: r for r in env["data"]["rows"]}
        assert "999999" in rows
        assert rows["999999"]["missing"] is True
        assert rows["999999"]["close"] is None

    def test_rows_carry_kline_date_and_as_of_is_max(self, ctx):
        """每行带自己的数据截止日（kline_date）；信封 as_of = 各行 max。

        行级截止时间是「这只票的数据到哪天」（停牌票停在停牌前），
        页顶「截至」是全页已知的最大值——批量返回的外层表 as_of_of
        认不出，日期必须从行里收回来。
        """
        env = run(ctx, "watchlist", {"symbols": "600519,000001"})
        rows = env["data"]["rows"]
        assert all(r.get("kline_date") for r in rows)
        assert env["as_of"] == max(r["kline_date"] for r in rows)

    def test_as_of_is_max_when_row_dates_differ(self, ctx):
        """有的票停在更早的日期（停牌），信封 as_of 仍取最大——页顶
        不能被一只停牌票拖回旧日期。

        live 伴取合并的规则：live 日期**不早于**快照日期才覆盖——停牌票
        的 live 停在更早日期时，行日期保留快照值（现价不能倒回停牌前）。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "600519": {"symbol": "600519", "name": "贵州茅台", "close": 1460.0,
                       "percent": 0.01, "chg_5d": 0.03, "chg_20d": 0.06,
                       "vol_ratio_5": 1.1, "kline_date": "2026-11-24"},
            "000001": {"symbol": "000001", "name": "平安银行", "close": 11.8,
                       "percent": -0.005, "chg_5d": -0.01, "chg_20d": -0.02,
                       "vol_ratio_5": 0.9, "kline_date": "2026-11-10"},
        }
        ctx.fetcher._override["kline.query_last_live_many"] = {
            "600519": {"date": "2026-11-24", "close": 1455.0},
            "000001": {"date": "2026-11-10", "close": 11.7},
        }
        env = run(ctx, "watchlist", {"symbols": "600519,000001"})
        assert env["as_of"] == "2026-11-24"
        dates = {r["symbol"]: r["kline_date"] for r in env["data"]["rows"]}
        assert dates == {"600519": "2026-11-24", "000001": "2026-11-10"}

    def test_live_merge_overrides_price_when_newer(self, ctx):
        """live=true：live 日期更新（≥快照）时现价/涨跌幅以 live 为准并标
        live；live 日期更早（停牌票）时**不覆盖**——现价不能倒回停牌前。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "600519": {"symbol": "600519", "name": "贵州茅台",
                       "close": 1474.84, "percent": 0.0102, "amount": 1.0,
                       "mv": 2.0, "chg_5d": 0.03, "chg_20d": 0.06,
                       "vol_ratio_5": 1.1, "kline_date": "2026-11-25"},
            "000001": {"symbol": "000001", "name": "平安银行",
                       "close": 12.4, "percent": 0.008, "amount": 1.0,
                       "mv": 2.0, "chg_5d": 0.01, "chg_20d": 0.02,
                       "vol_ratio_5": 0.9, "kline_date": "2026-11-26"},
        }
        ctx.fetcher._override["kline.query_last_live_many"] = {
            "600519": {"date": "2026-11-26", "close": 1463.56,
                       "percent": -0.0076, "amount": 8.6, "mv": 2.1},
            "000001": {"date": "2026-11-25", "close": 99.0,
                       "percent": 0.5, "amount": 9.9, "mv": 9.9},
        }
        env = run(ctx, "watchlist", {"symbols": "600519,000001",
                                     "live": True})
        rows = {r["symbol"]: r for r in env["data"]["rows"]}
        assert rows["600519"]["live"] is True
        assert rows["600519"]["close"] == 1463.56, "live 更新 → 现价覆盖"
        assert rows["600519"]["kline_date"] == "2026-11-26"
        assert rows["000001"].get("live") is not True
        assert rows["000001"]["close"] == 12.4, "live 更早（停牌）→ 不覆盖"

    def test_live_off_keeps_snapshot_values(self, ctx):
        """live=false（默认）：live_many 只补日期，现价保持快照值。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "600519": {"symbol": "600519", "name": "贵州茅台",
                       "close": 1474.84, "percent": 0.0102,
                       "kline_date": "2026-11-25"},
        }
        ctx.fetcher._override["kline.query_last_live_many"] = {
            "600519": {"date": "2026-11-26", "close": 1463.56},
        }
        env = run(ctx, "watchlist", {"symbols": "600519"})
        row = env["data"]["rows"][0]
        assert row["close"] == 1474.84
        assert row["kline_date"] == "2026-11-26", "日期伴取仍生效"
        assert "live" not in row

    def test_dedup_symbols(self, ctx):
        env = run(ctx, "watchlist", {"symbols": "600519,600519,000001"})
        assert env["data"]["symbols"] == ["600519", "000001"]

    def test_default_symbols_when_empty(self, ctx):
        env = run(ctx, "watchlist", {})
        assert env["data"]["symbols"], "空清单要有示例标的，不能是空页"
        assert env["data"]["count"] > 0

    def test_columns_have_labels(self, ctx):
        env = run(ctx, "watchlist", {})
        for col in env["data"]["columns"]:
            assert col["key"] and col["label"]


# --------------------------------------------------------------------------
# 行情
# --------------------------------------------------------------------------

class TestMarkets:
    def test_trading_day_from_index_last_bar(self, ctx):
        """「最新交易日」是推断口径（沪深300最新K线日），且**不冒充**信封
        as_of——上游宽度/资金流没有任何日期字段，数据截止只能如实为空。"""
        # 指数K线给一个比演示截止日更新的日期：as_of 不得跟着变
        ctx.fetcher._override["kline.bars"] = [
            {"date": "2026-12-31", "open": 1, "high": 1, "low": 1, "close": 1},
        ]
        env = run(ctx, "markets", {})
        envelope_ok(env)
        assert env["data"]["trading_day"] == "2026-12-31"
        assert env["as_of"] != "2026-12-31", "交易日历事实不得顶替数据截止"

    def test_trading_day_failure_degrades(self, ctx):
        """指数K线取不到 → trading_day 缺省（前端回落「截至未知」），
        整页行情不跟着失败。"""
        original = ctx.fetcher.facade

        def broken(ns, method, **params):
            if (ns, method) == ("kline", "bars"):
                raise RuntimeError("upstream down")
            return original(ns, method, **params)

        ctx.fetcher.facade = broken
        env = run(ctx, "markets", {})
        assert env["ok"] is True
        assert env["data"]["trading_day"] == ""
        assert env["data"]["kpi"], "行情主体数据不受日期参照失败影响"

    def test_kpi_present(self, ctx):
        env = run(ctx, "markets", {})
        envelope_ok(env)
        assert env["ok"] is True
        kpi = env["data"]["kpi"]
        assert "up" in kpi and "down" in kpi
        assert "limit_up" in kpi

    def test_counts_are_numbers_not_strings(self, ctx):
        """分桶计数必须是数字——前端要按它画柱状图并排序。"""
        env = run(ctx, "markets", {})
        for row in env["data"]["bins"]:
            assert isinstance(row["count"], int), f"{row} 的 count 不是整数"

    def test_movers_respect_limit(self, ctx):
        env = run(ctx, "markets", {"limit": 3})
        assert len(env["data"]["movers"]) <= 3

    def test_moneyflow_sorted_by_net_amount(self, ctx):
        """资金流按净额降序，**不按市值占比**（后者会让小盘股永远在前）。"""
        env = run(ctx, "markets", {"limit": 5})
        values = [r["net_mf"] for r in env["data"]["moneyflow"]]
        assert values == sorted(values, reverse=True)


# --------------------------------------------------------------------------
# 宏观
# --------------------------------------------------------------------------

class TestEconomics:
    def test_three_blocks_independent(self, ctx):
        """三块数据都在（宏观序列 / 曲线 / 汇率）。"""
        env = run(ctx, "economics", {})
        envelope_ok(env)
        assert env["ok"] is True
        assert env["data"]["series"]
        assert env["data"]["curve"]
        assert env["data"]["fx"]

    def test_curve_not_interpolated(self, ctx):
        """曲线只含真实披露的期限，不做插值（插值会造出不存在的点）。"""
        from workbench.tools.economics.handler import TENORS

        env = run(ctx, "economics", {})
        tenors = [p["tenor"] for p in env["data"]["curve"]]
        # 期限是**领域顺序**（1/3/5/7/10/30 年），不是字典序——
        # 字典序会把 "10年" 排到 "1年" 前面。
        assert tenors == [t for t in TENORS if t in set(tenors)]
        for p in env["data"]["curve"]:
            assert p["yield"] is not None

    def test_curve_values_differ_by_tenor(self, ctx):
        """各期限收益率必须不同——全一样会让「曲线是平的」看起来像事实。"""
        env = run(ctx, "economics", {})
        values = [round(p["yield"], 6) for p in env["data"]["curve"]]
        assert len(set(values)) > 1, f"曲线各期限收益率全相同：{values}"

    def test_series_ascending(self, ctx):
        env = run(ctx, "economics", {})
        sas = [p["sas"] for p in env["data"]["series"]]
        assert sas == sorted(sas), "宏观序列应按 sas 升序（旧→新）"

    def test_code_switch_changes_request(self, ctx):
        env = run(ctx, "economics", {"code": "$PPI"})
        assert env["data"]["code"] == "$PPI"

    def test_bad_macro_code_degrades_not_crash(self, ctx):
        """未知指标码 → 序列为空带说明，但页面不整体失败。"""
        env = run(ctx, "economics", {"code": "$NOT_EXIST"})
        assert env["ok"] is True
        assert env["data"]["series"] == []
        assert "无可用" in env["data"]["series_note"] or env["warnings"]

    def test_series_accepts_real_flat_desc_shape(self, ctx):
        """真实 ``macro.query`` 是**扁平 dict**（series 顶层、无 data 信封、
        新→旧）——旧夹具曾按信封形+旧→新捏，真实模式序列块恒「返回结构
        异常」（D-27）。handler 两种形状都认，顺序统一归一为升序。"""
        ctx.fetcher._override["macro.query"] = {
            "ok": True, "frequency": "month", "periods": 3,
            "metric": "$CPI", "store": "cpi",
            "latest": {"annual": 2026, "sampling": "M10",
                       "sas": "2026:M10", "value": 100.7},
            "series": [
                {"annual": 2026, "sampling": "M10",
                 "sas": "2026:M10", "value": 100.7},
                {"annual": 2026, "sampling": "M09",
                 "sas": "2026:M09", "value": 100.2},
                {"annual": 2026, "sampling": "M08",
                 "sas": "2026:M08", "value": 99.8},
            ],
        }
        env = run(ctx, "economics", {"code": "$CPI", "n": 3})
        assert env["ok"] is True
        series = env["data"]["series"]
        sas = [p["sas"] for p in series]
        assert sas == ["2026:M08", "2026:M09", "2026:M10"], \
            "真实新→旧的点必须归一为旧→新"
        assert "month 频 · 最新 2026:M10" in env["data"]["series_note"]

    def test_all_null_skeleton_points_mean_unavailable(self, ctx):
        """真实未知码不报错，返回 value 全 None 的骨架点——归为「无可用值」，
        不让「码拼错」看起来像有数据。"""
        ctx.fetcher._override["macro.query"] = {
            "ok": True, "frequency": "month", "periods": 2,
            "metric": "$NOPE", "store": "",
            "latest": {"annual": 2026, "sampling": "M10",
                       "sas": "2026:M10", "value": None},
            "series": [
                {"annual": 2026, "sampling": "M10",
                 "sas": "2026:M10", "value": None},
                {"annual": 2026, "sampling": "M09",
                 "sas": "2026:M09", "value": None},
            ],
        }
        env = run(ctx, "economics", {"code": "$NOPE"})
        assert env["ok"] is True
        assert env["data"]["series"] == []
        assert "无可用值" in env["data"]["series_note"]


# --------------------------------------------------------------------------
# 回测
# --------------------------------------------------------------------------

class TestBacktest:
    def test_requires_range(self, ctx):
        """不给区间必须拒绝——全历史单次可达数十万 EC。"""
        before = len(ctx.fetcher.calls)
        env = run(ctx, "backtest", {"symbol": "600519"})
        envelope_ok(env)
        assert env["ok"] is False
        assert env["meta"]["code"] == "need_range"
        assert len(ctx.fetcher.calls) == before, "拒绝时必须零请求"

    def test_runs_with_range(self, ctx):
        env = run(ctx, "backtest", {"symbol": "600519",
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        envelope_ok(env)
        assert env["ok"] is True
        data = env["data"]
        assert data["trades"]
        assert data["equity"]
        assert data["summary"]

    def test_summary_has_eight_numbers(self, ctx):
        """``summary`` 是八个数字（不多不少，缺的不补 0）。"""
        env = run(ctx, "backtest", {"symbol": "600519",
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        labels = env["data"]["summary_labels"]
        assert len(labels) == 8
        for item in labels:
            assert item["key"] and item["label"] and item["format"]

    def test_summary_labels_all_populated(self, ctx):
        """八个标签**每一个都要有值**——只数标签数会放过「四项恒为 —」。

        真事（2026-11-26）：``SUMMARY_LABELS`` 写的是 ``annual_return`` /
        ``trades`` / ``final_nav`` / ``total_fee``，而上游 ``summary`` 给的是
        ``cagr`` / ``n_trades``，且不返回后两个。标签数对、页面却四项空着。
        """
        env = run(ctx, "backtest", {"symbol": "600519",
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        summary = env["data"]["summary"]
        missing = [lbl["key"] for lbl in env["data"]["summary_labels"]
                   if summary.get(lbl["key"]) is None]
        assert not missing, f"这些汇总项没有值（页面会渲染成 —）：{missing}"

    def test_summary_derives_nav_and_fee_locally(self, ctx):
        """上游不给 ``final_nav`` / ``total_fee``，必须由本地数据现算出来。"""
        env = run(ctx, "backtest", {"symbol": "600519",
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        data = env["data"]
        assert data["summary"]["final_nav"] == data["equity"][-1]["nav"]
        assert data["summary"]["total_fee"] == pytest.approx(
            sum(t["fee"] for t in data["trades"]))
        # 明细腿数可对账：页面显示的数字必须等于明细表行数
        assert data["summary"]["n_trades"] == len(data["trades"])

    def test_ma_cross_rejects_fast_ge_slow(self, ctx):
        env = run(ctx, "backtest", {"symbol": "600519", "fast": 20, "slow": 5,
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        assert env["ok"] is False
        assert env["meta"]["action"] == "fix_input"

    def test_valuation_rule_requires_thresholds(self, ctx):
        env = run(ctx, "backtest", {"symbol": "600519", "rule": "pe",
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        assert env["ok"] is False
        assert env["meta"]["code"] == "missing_param"

    def test_valuation_rule_with_thresholds(self, ctx):
        env = run(ctx, "backtest", {"symbol": "600519", "rule": "pe",
                                    "buy": 20, "sell": 40,
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        assert env["ok"] is True
        assert env["data"]["params"]["buy"] == pytest.approx(20.0)

    def test_invalid_rule_rejected(self, ctx):
        env = run(ctx, "backtest", {"symbol": "600519", "rule": "magic",
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        assert env["ok"] is False

    def test_normalize_bars(self, ctx):
        """降序输入（真实 ``kline.query_bars`` 是新→旧）→ 升序输出；
        缺 OHLC 的行丢掉并计数——不画假实体，也不静默。"""
        from workbench.tools._shared import normalize_bars
        rows, skipped = normalize_bars([
            {"date": "2026-11-20", "open": 2, "high": 3, "low": 1, "close": 2.5},
            {"date": "2026-11-18", "open": 1, "high": 2, "low": 0.5, "close": 1.5},
            {"date": "2026-11-19", "open": "x", "high": 2, "low": 1, "close": 1.5},
        ])
        assert [r["date"] for r in rows] == ["2026-11-18", "2026-11-20"]
        assert skipped == 1

    def test_marks_carried_even_with_unknown_side(self, ctx):
        """``side`` 原样透传：上游换枚举时「买卖点莫名变少」比
        「长出一个菱形」更糟——未知值必须可见。"""
        ctx.fetcher._override["backtest.run"] = {
            "trades": [{"date": "2026-11-18", "side": "hold", "price": 100.0},
                       {"date": "2026-11-19", "side": "buy", "price": 101.5}],
            "equity": [{"date": "2026-11-18", "nav": 1_000_000.0}],
            "summary": {"total_return": 0.0},
        }
        env = run(ctx, "backtest", {"symbol": "600519",
                                    "begin": "2026-01-01", "end": "2026-11-20"})
        sides = [m["side"] for m in env["data"]["marks"]]
        assert sides == ["hold", "buy"], "未知 side 不得静默丢弃"

    def test_price_bars_added_and_disclosed(self, ctx):
        """价格 K 线是**另一次** ``kline.bars`` 取数——meta 里必须披露，
        让「多花的这一次请求」可被看见。"""
        env = run(ctx, "backtest", {"symbol": "600519",
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        assert env["ok"] is True
        assert env["data"]["bars"], "演示态应能取到区间 K 线"
        assert "kline.bars" in env["meta"]["note"]
        assert "kline.bars" in [t for t, _ in ctx.fetcher.calls]

    def test_price_bars_failure_degrades(self, ctx):
        """K 线失败只降级「标在价格上」，不毁掉已到手的回测结果。"""
        original = ctx.fetcher.facade

        def broken(ns, method, **params):
            if (ns, method) == ("kline", "bars"):
                raise RuntimeError("upstream down")
            return original(ns, method, **params)

        ctx.fetcher.facade = broken
        env = run(ctx, "backtest", {"symbol": "600519",
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        assert env["ok"] is True
        assert env["data"]["bars"] == []
        assert any("价格 K 线未取到" in w for w in env["warnings"])

    def test_as_of_is_data_last_date_not_requested_end(self, ctx):
        """信封 as_of = 数据实际末日（净值/价格取最大），不是请求的 end
        参数——end 是「声称的区间」，上游可能没有数据到那天。"""
        ctx.fetcher._override["backtest.run"] = {
            "trades": [{"date": "2026-01-06", "side": "buy", "price": 100.0}],
            "equity": [{"date": "2026-01-06", "nav": 1_000_000.0},
                       {"date": "2026-03-31", "nav": 1_050_000.0}],
            "summary": {"total_return": 0.05},
        }
        ctx.fetcher._override["kline.bars"] = [
            {"date": "2026-01-02", "open": 100, "high": 101, "low": 99,
             "close": 100.5},
            {"date": "2026-01-06", "open": 100.5, "high": 103, "low": 100,
             "close": 102.0},
        ]
        env = run(ctx, "backtest", {"symbol": "600519",
                                    "begin": "2026-01-01", "end": "2026-11-20"})
        assert env["as_of"] == "2026-03-31", (
            f"应取净值实际末日，收到 {env['as_of']!r}（end 参数是 2026-11-20）")

    def test_as_of_falls_back_to_end_when_no_dates(self, ctx):
        """两路都没有日期（极端失败）时才回落 end 参数——回落是底线，
        不是首选。"""
        ctx.fetcher._override["backtest.run"] = {
            "trades": [], "equity": [], "summary": {},
        }
        ctx.fetcher._override["kline.bars"] = []
        env = run(ctx, "backtest", {"symbol": "600519",
                                    "begin": "2025-01-01", "end": "2026-11-20"})
        assert env["as_of"] == "2026-11-20"


# --------------------------------------------------------------------------
# 驾驶舱
# --------------------------------------------------------------------------

class TestDashboard:
    #: Manual 级（付费重）目标——首屏绝不允许出现。
    MANUAL_TARGETS = frozenset({
        "dividend.decomp", "screener.query", "valuation.daily_basic",
        "pdf_doc.read_markdown", "moneyflow.universe",
        "backtest.run",
    })

    def test_no_manual_calls(self, ctx):
        """**核心验收**：首屏不得发任何付费重请求。

        驾驶舱是打开就自动跑的首屏。这里挂一个 Manual 调用，用户每开
        一次工作台都在花钱，而界面上看不出任何异常。
        """
        before = len(ctx.fetcher.calls)
        env = run(ctx, "dashboard", {})
        envelope_ok(env)
        called = {t for t, _ in ctx.fetcher.calls[before:]}
        assert not (called & self.MANUAL_TARGETS), \
            f"驾驶舱发了 Manual 级调用：{sorted(called & self.MANUAL_TARGETS)}"
        assert env["data"]["manual_calls"] == 0

    def test_three_blocks_present(self, ctx):
        env = run(ctx, "dashboard", {})
        assert env["ok"] is True
        assert env["data"]["indices"]
        assert env["data"]["breadth"]
        assert env["data"]["moneyflow"]

    def test_index_valuations_have_pe_pb(self, ctx):
        env = run(ctx, "dashboard", {})
        for row in env["data"]["indices"]:
            assert row["key"].startswith("index.")
            assert row["label"]
            assert row["pe"] is not None

    def test_indices_as_of_is_a_date_from_trend_points(self, ctx):
        """指数估值块要带**PE/PB 数据日**（index.trend 升序 points 末行）。

        此前整卡走 ``indices.valuation``（季度末采样），页上永远「截至
        9-30」；换 trend 后这里是最新交易日。演示数据曾用 ``2026-Q4``
        期点标签（与真实 ``YYYY-MM-DD`` 不同形，D-27），焊住「必须是日期」。
        """
        env = run(ctx, "dashboard", {})
        as_of = env["data"]["indices_as_of"]
        assert len(as_of) == 10 and as_of[4] == "-", f"必须是日期，收到 {as_of!r}"

    def test_dv_as_of_is_quarter_end_date(self, ctx):
        """股息率（与季度回退口径）单独给季度末日期——它只有季频源，
        不能与 PE/PB 的最新交易日混在一个日期里。"""
        env = run(ctx, "dashboard", {})
        dv_as_of = env["data"]["dv_as_of"]
        assert len(dv_as_of) == 10 and dv_as_of[4] == "-", \
            f"必须是日期，收到 {dv_as_of!r}"

    def test_pe_pb_from_trend_latest_point(self, ctx):
        """PE/PB 取 ``index.trend`` 升序 points 的**末行**（最新交易日），
        不再是季度末 current——这是「估值停在 9-30」的修复本体。"""
        original_facade = ctx.fetcher.facade

        def trend_envelope(ns, method, **params):
            if (ns, method) == ("index", "trend"):
                return {"ok": True, "as_of": "2026-11-25",
                        "data": {"key": params.get("key"), "points": [
                            {"date": "2026-11-18", "pe": 13.0, "pb": 1.20},
                            {"date": "2026-11-25", "pe": 13.32, "pb": 1.2285},
                        ]}, "meta": {}}
            return original_facade(ns, method, **params)

        ctx.fetcher.facade = trend_envelope
        env = run(ctx, "dashboard", {})
        hs = next(r for r in env["data"]["indices"]
                  if r["key"] == "index.hs300")
        assert hs["pe"] == 13.32 and hs["pb"] == 1.2285
        assert hs["pe_date"] == "2026-11-25"
        assert hs["quarterly"] is False
        assert env["data"]["indices_as_of"] == "2026-11-25"

    def test_cyb_falls_back_to_quarterly_with_warning(self, ctx):
        """trend 不覆盖的指数（真实如创业板指 0 行）→ 回退季度末 current，
        行标 quarterly 并告警——**回退口径必须可见**，否则季末数据会被
        当成今日值。演示里 cyb 的 indices.valuation 也如实未供数（镜像
        真实），所以这里注入一份有值的季度口径来驱动回退分支。"""
        original_facade = ctx.fetcher.facade
        original_call = ctx.fetcher.call

        def no_cyb_trend(ns, method, **params):
            if ((ns, method) == ("index", "trend")
                    and params.get("key") == "index.cyb"):
                return {"ok": True, "as_of": "",
                        "data": {"key": "index.cyb", "points": []},
                        "meta": {}}
            return original_facade(ns, method, **params)

        def cyb_quarterly(target, **params):
            if target == "indices.valuation" and params.get("key") == "index.cyb":
                return {"current": {"pe": 41.2, "pb": 4.38, "dv": 0.0062},
                        "series": [{"d": "2026-09-30", "pe": 41.2,
                                    "pb": 4.38}]}
            return original_call(target, **params)

        ctx.fetcher.facade = no_cyb_trend
        ctx.fetcher.call = cyb_quarterly
        env = run(ctx, "dashboard", {})
        cyb = next(r for r in env["data"]["indices"]
                   if r["key"] == "index.cyb")
        assert cyb["quarterly"] is True
        assert cyb["pe"] == 41.2
        assert env["data"]["dv_as_of"] == "2026-09-30"
        assert any("季度末" in w for w in env["warnings"])

    def test_cyb_missing_when_neither_source_has_data(self, ctx):
        """两路都没有数据（真实 cyb：trend 0 行且 valuation 未供数）→
        如实缺失并告警，**不编数值**。"""
        env = run(ctx, "dashboard", {})
        keys = {r["key"] for r in env["data"]["indices"]}
        assert "index.cyb" not in keys
        assert any("指数估值缺" in w for w in env["warnings"])

    def test_index_cards_live_with_date_guard(self, ctx):
        """盘面三卡：date 守卫必须挡兜底假行——上游对断供键（cyb）返回
        date 停在上一交易日的假行（2026-11-26 午休实测，与 index.bogus
        逐位同值），不设防会把昨天画成今天。真行（date=最新交易日）出卡
        且带分时 mini。"""
        from shape_gen import SHAPE_AS_OF
        ctx.fetcher._override["kline.query_index_last_live_many"] = {
            "index.shzs": {"close": 3475.36, "percent": -0.0003,
                           "change": -1.11, "high": 3497.81, "low": 3469.65,
                           "date": SHAPE_AS_OF},
            "index.szcz": {"close": 10102.04, "percent": 0.0016,
                           "change": 15.68, "high": 10235.5, "low": 10094.17,
                           "date": SHAPE_AS_OF},
            # 兜底假行：与真行同形状，但 date 停在上一交易日
            "index.cyb": {"close": 3476.4697, "percent": -0.020263,
                          "change": -70.9, "high": 3526.3366,
                          "low": 3468.6523, "date": "2026-11-19"},
        }
        env = run(ctx, "dashboard", {})
        cards = env["data"]["index_cards"]
        assert [c["key"] for c in cards] == ["index.shzs", "index.szcz"], \
            "date 停在上一交易日的兜底行必须被守卫挡住"
        assert cards[0]["close"] == 3475.36
        assert cards[0]["minute"], "形状夹具已收录 shzs 分时，卡带 mini 序列"
        assert all("avg" not in p for c in cards for p in c["minute"]), \
            "指数分时不带均价（聚合量纲除出来不是价格）"

    def test_index_cards_default_three_keys(self, ctx):
        """默认夹具：三卡齐全（cyb 的 live 行 date=锚点日，守卫放行），
        但 cyb 无分时 mini——镜像真实上游缺口，不编小图。"""
        env = run(ctx, "dashboard", {})
        cards = {c["key"]: c for c in env["data"]["index_cards"]}
        assert set(cards) == {"index.shzs", "index.szcz", "index.cyb"}
        assert cards["index.shzs"]["minute"], "shzs 有分时"
        assert cards["index.szcz"]["minute"], "szcz 有分时"
        assert cards["index.cyb"]["minute"] == [], "cyb 分时上游无覆盖"

    def test_index_cards_failure_degrades(self, ctx, tmp_path):
        """指数盘中失败只丢卡片并告警，不拖垮首屏（全新上下文避缓存）。"""
        fresh = build_context(fetcher=FakeFetcher(resolver=shape_for), store=Store(tmp_path / "tile.db"))
        original_call = fresh.fetcher.call

        def boom(target, **params):
            if target == "kline.query_index_last_live_many":
                raise RuntimeError("boom")
            return original_call(target, **params)

        fresh.fetcher.call = boom
        env = fresh.registry["dashboard"](fresh, {})
        assert env["ok"] is True
        assert env["data"]["index_cards"] == []
        assert any("指数盘中" in w for w in env["warnings"])

    def test_distribution_blocks_present(self, ctx):
        """涨跌分布直方图 + 涨跌幅双榜：夹具同源（bins/movers）出数，
        且指数不再进 KpiStrip 载荷（盘面三卡取代）。"""
        env = run(ctx, "dashboard", {})
        dist = env["data"]["distribution"]
        assert len(dist.get("bins") or []) >= 1
        assert dist.get("gainers") and dist.get("losers"), "双榜都要有"
        assert "index_tiles" not in env["data"], "旧指数 chips 已移除"

    def test_distribution_failure_degrades(self, ctx, tmp_path):
        """分布/双榜失败只降级为空块 + 告警，首屏不塌（全新上下文）。

        bins/movers 是**组合门面**（走 ``fetcher.facade``），拦截点在那里。"""
        fresh = build_context(fetcher=FakeFetcher(resolver=shape_for), store=Store(tmp_path / "dist.db"))
        original_facade = fresh.fetcher.facade

        def boom(ns, method, **params):
            if (ns, method) in (("screener", "index_breadth_bins"),
                                ("screener", "index_top_movers")):
                raise RuntimeError("boom")
            return original_facade(ns, method, **params)

        fresh.fetcher.facade = boom
        env = fresh.registry["dashboard"](fresh, {})
        assert env["ok"] is True
        dist = env["data"]["distribution"]
        assert dist.get("bins") == [] and not dist.get("gainers")
        assert any("分布" in w or "榜" in w for w in env["warnings"])

    def test_trading_day_present_and_degrades(self, ctx, tmp_path):
        """页级「最新交易日」为推断口径：正常给值；取不到时缺省但页面不崩
        （宽度/资金流上游没有日期字段，chip 回落「截至未知」）。"""
        env = run(ctx, "dashboard", {})
        assert env["ok"] is True
        assert env["data"]["trading_day"]
        assert "trading_day" in (env["meta"].get("note") or "")

        # 降级要在**全新上下文**里测：hub 按 target+params 缓存，同 ctx
        # 重跑会命中上一次的缓存而根本不走到失败路径
        fresh = build_context(fetcher=FakeFetcher(resolver=shape_for), store=Store(tmp_path / "degrade.db"))
        original_facade = fresh.fetcher.facade

        def failing_bars(ns, method, **params):
            if (ns, method) == ("kline", "bars"):
                raise RuntimeError("boom")
            return original_facade(ns, method, **params)

        fresh.fetcher.facade = failing_bars
        degraded = fresh.registry["dashboard"](fresh, {})
        assert degraded["ok"] is True
        # 日 K 失败但盘面卡有日期 → 回落卡日期（推断升级：两源取较大者）
        from shape_gen import SHAPE_AS_OF
        assert degraded["data"]["trading_day"] == SHAPE_AS_OF

    def test_trading_day_takes_fresher_card_date(self, ctx):
        """推断口径取 max（指数K线日, 盘面卡日期）：指数日 K **盘后才
        物化**，盘中恒滞后一天——页头「11-25」与盘面三卡「11-26」曾在
        同页打架（实时与非实时混在一个口径里）。"""
        ctx.fetcher._override["kline.bars"] = [{"date": "2026-11-01"}]
        env = run(ctx, "dashboard", {})
        from shape_gen import SHAPE_AS_OF
        assert env["data"]["trading_day"] == SHAPE_AS_OF, \
            "盘面快照日期比滞后的日 K 新，必须取较大者"

    def test_trading_day_empty_when_all_dates_fail(self, ctx, tmp_path):
        """两个日期源都失败 → 缺省（chip 回落「截至未知」），不编日期。"""
        fresh = build_context(fetcher=FakeFetcher(resolver=shape_for), store=Store(tmp_path / "alldates.db"))
        original_facade = fresh.fetcher.facade
        original_call = fresh.fetcher.call

        def failing_facade(ns, method, **params):
            if (ns, method) == ("kline", "bars"):
                raise RuntimeError("boom")
            return original_facade(ns, method, **params)

        def failing_call(target, **params):
            if target == "kline.query_index_last_live_many":
                raise RuntimeError("boom")
            return original_call(target, **params)

        fresh.fetcher.facade = failing_facade
        fresh.fetcher.call = failing_call
        env = fresh.registry["dashboard"](fresh, {})
        assert env["ok"] is True
        assert env["data"]["trading_day"] == ""

    def test_missing_valuation_degrades(self, ctx):
        """某指数取不到估值 → 其余照常，并给出告警。"""
        original = ctx.fetcher.call

        def flaky(target, **params):
            if target == "indices.valuation" and params.get("key") == "index.hk":
                raise RuntimeError("boom")
            return original(target, **params)

        ctx.fetcher.call = flaky
        env = run(ctx, "dashboard", {})
        assert env["ok"] is True


# --------------------------------------------------------------------------
# 选股
# --------------------------------------------------------------------------

class TestScreener:
    def test_nested_envelope_shape_extracts_rows(self, ctx):
        """真实 ``cli.screener.query`` 返回**统一信封**：行在 ``data.rows``
        （DataFrame）、命中数在 ``data.count``——handler 读顶层 ``rows``
        曾导致真实模式恒空（旧夹具扁平 dict 全绿，D-25/D-27）。"""
        ctx.fetcher._override["screener.query"] = {
            "ok": True,
            "as_of": "",
            "data": {
                "count": 428,
                "rows": [
                    {"symbol": "600519", "name": "贵州茅台", "$PE_TTM": 14.2},
                    {"symbol": "000001", "name": "平安银行", "$PE_TTM": 4.9},
                ],
            },
        }
        env = run(ctx, "screener", {"where": "$PE_TTM < 15", "limit": 5})
        assert env["ok"] is True
        assert env["data"]["total"] == 428, "命中数取 data.count（全市场，非 topN）"
        assert [r["symbol"] for r in env["data"]["rows"]] == ["600519", "000001"]

    def test_rejects_python_boolean_words(self, ctx):
        """``and``/``or``/``not`` 本地拦截，并提示正确写法。"""
        for expr, hint in (("$PE_TTM < 15 and $PB < 3", "&&"),
                          ("$PE_TTM < 15 or $PB < 3", "||"),
                          ("not $PE_TTM < 15", "!")):
            before = len(ctx.fetcher.calls)
            env = run(ctx, "screener", {"where": expr})
            assert env["ok"] is False, expr
            assert hint in env["meta"]["error"]
            assert len(ctx.fetcher.calls) == before, "拦截时必须零请求"

    def test_runs_simple_expression(self, ctx):
        env = run(ctx, "screener", {"where": "$PE_TTM < 15", "limit": 5})
        envelope_ok(env)
        assert env["ok"] is True
        # 默认非负守卫：实际执行的是守卫后的表达式
        assert env["data"]["where"] == "($PE_TTM < 15) && $PE_TTM > 0"
        assert "rows" in env["data"]

    def test_non_negative_guard_appended_by_default(self, ctx):
        """**非负守卫默认开**：亏损股的负 PE 不再混进「低估值」。

        服务端追加而不是客户端过滤——省 EC，被守卫挡掉的行根本不计费；
        追加了什么必须如实披露。"""
        env = run(ctx, "screener", {"where": "$PE_TTM < 15", "limit": 5})
        sent = dict(ctx.fetcher.calls[-1][1])["where"]
        assert sent == "($PE_TTM < 15) && $PE_TTM > 0"
        assert any("非负守卫" in w and "$PE_TTM > 0" in w
                   for w in env["warnings"]), "必须披露追加了什么"

    def test_non_negative_guard_can_be_turned_off(self, ctx):
        env = run(ctx, "screener", {"where": "$PE_TTM < 15",
                                    "exclude_negative": False})
        sent = dict(ctx.fetcher.calls[-1][1])["where"]
        assert sent == "$PE_TTM < 15", "显式关掉后不得改写表达式"
        assert not [w for w in env.get("warnings") or [] if "非负" in w]

    def test_non_negative_guard_dedupes_and_covers_order(self, ctx):
        """where+order 引用的指标全部入保，重复引用只追加一次。"""
        env = run(ctx, "screener", {"where": "$PE_TTM < 15",
                                    "order": "$PE_TTM",
                                    "limit": 5})
        sent = dict(ctx.fetcher.calls[-1][1])["where"]
        assert "$PE_TTM > 0" in sent
        assert sent.count("> 0") == 1, "同一指标只追加一次"

    def test_non_negative_guard_covers_order_metric(self, ctx):
        env = run(ctx, "screener", {"where": "$PE_TTM < 15",
                                    "order": "$ID_BONUS_RATE_TTM",
                                    "limit": 5})
        sent = dict(ctx.fetcher.calls[-1][1])["where"]
        assert sent == "($PE_TTM < 15) && $PE_TTM > 0 && $ID_BONUS_RATE_TTM > 0"

    def test_non_negative_guard_skips_explicit_positive_clause(self, ctx):
        """用户已写 ``$X > 0`` 的指标不重复追加；全部已写时表达式零改动。"""
        env = run(ctx, "screener",
                  {"where": "$PE_TTM > 0 && $PE_TTM < 15"})
        sent = dict(ctx.fetcher.calls[-1][1])["where"]
        assert sent == "$PE_TTM > 0 && $PE_TTM < 15"
        assert not [w for w in env.get("warnings") or [] if "非负" in w]

    def test_non_negative_guard_wraps_or_expression(self, ctx):
        """``||`` 表达式必须先加括号再 && ——否则优先级把守卫变成摆设。"""
        env = run(ctx, "screener", {"where": "$PE_TTM < 10 || $PB < 1"})
        sent = dict(ctx.fetcher.calls[-1][1])["where"]
        assert sent == "($PE_TTM < 10 || $PB < 1) && $PE_TTM > 0 && $PB > 0"

    def test_non_negative_guard_skips_boolean_flags(self, ctx):
        """``!$IS_ST`` 不能再被 ``$IS_ST > 0`` 打死——布尔标志位不适用非负守卫。"""
        env = run(ctx, "screener",
                  {"where": "$ROIC_10Y_MIN_LAST > 0.15 && !$IS_ST && !$IS_BANK",
                   "limit": 5})
        sent = dict(ctx.fetcher.calls[-1][1])["where"]
        assert "$IS_ST > 0" not in sent
        assert "$IS_BANK > 0" not in sent
        assert "$ROIC_10Y_MIN_LAST > 0" in sent

    def test_non_negative_guard_keeps_zero_for_balance_sheet_ratios(self, ctx):
        """商誉/有息负债为 0 是「好」，守卫只能排除负值（含浮点零）。"""
        env = run(ctx, "screener",
                  {"where": "$GW_RATE_LAST < 0.05 && $IBD_RATE_LAST < 0.30",
                   "limit": 5})
        sent = dict(ctx.fetcher.calls[-1][1])["where"]
        assert "$GW_RATE_LAST >= -0.000001" in sent
        assert "$IBD_RATE_LAST >= -0.000001" in sent
        assert "$GW_RATE_LAST > 0" not in sent

    def test_low_pe_preset_carries_positive_clause(self):
        """低估值示例自带 ``> 0``：示例本身就应该是安全的写法。"""
        from workbench.tools.screener.handler import PRESET_SCREENS

        preset = next(p for p in PRESET_SCREENS if "PE_TTM" in p["where"])
        assert "$PE_TTM > 0" in preset["where"]

    def test_zero_request_when_over_budget(self, ctx):
        """预估超预算且未确认 → **零请求**。

        这是「花钱之前先算账」的硬要求：不是先发再检查，是压根不发。
        """
        ctx.fetcher.cost_estimate = lambda t, **p: {
            "ec_lo": 100_000, "ec_hi": 600_000, "model": "test"}
        before = len(ctx.fetcher.calls)
        env = run(ctx, "screener", {"where": "$PE_TTM < 15"})
        assert env["ok"] is True
        assert env["data"]["needs_confirm"] is True
        assert len(ctx.fetcher.calls) == before, "待确认时必须零请求"

    def test_runs_after_confirm(self, ctx):
        ctx.fetcher.cost_estimate = lambda t, **p: {
            "ec_lo": 100_000, "ec_hi": 600_000, "model": "test"}
        env = run(ctx, "screener", {"where": "$PE_TTM < 15", "confirmed": True})
        assert env["ok"] is True
        assert env["data"]["needs_confirm"] is False

    def test_save_and_list(self, ctx):
        run(ctx, "screener", {"where": "$PE_TTM < 20", "save_as": "低估值"})
        env = run(ctx, "screener", {"where": "$PE_TTM < 20"})
        names = [s["name"] for s in env["data"]["saved"]]
        assert "低估值" in names

    def test_presets_are_not_recommendations(self, ctx):
        """内置示例的名字必须带「示例：」前缀——避免被读成推荐策略。"""
        env = run(ctx, "screener", {"where": "$PE_TTM < 15"})
        for preset in env["data"]["presets"]:
            assert preset["name"].startswith("示例"), preset

    def test_missing_expression(self, ctx):
        env = run(ctx, "screener", {})
        assert env["ok"] is False
        assert env["meta"]["code"] == "missing_param"


# --------------------------------------------------------------------------
# 个股研究
# --------------------------------------------------------------------------

class TestEquity:
    def test_default_section_is_overview(self, ctx):
        env = run(ctx, "equity", {"symbol": "600519"})
        envelope_ok(env)
        assert env["ok"] is True
        assert env["data"]["section"] == "overview"
        assert env["data"]["data"]["snapshot"]["name"] == "贵州茅台"

    def test_overview_live_merge_when_newer(self, ctx):
        """概览盘中现价：``kline.snapshot`` 是**上一已完成交易日**（盘中
        打开页顶停在昨天，2026-11-26 用户实测），``query_last_live`` 日期
        严格新于快照日才覆盖现价并标 live，信封 as_of 提到今天。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "symbol": "600519", "name": "贵州茅台", "close": 1474.84,
            "percent": 0.0102, "mv": 2.0, "kline_date": "2026-11-25"}
        ctx.fetcher._override["kline.query_last_live"] = {
            "symbol": "600519", "close": 1460.65, "percent": -0.0096,
            "amount": 2.004e9, "mv": 1.826e12, "date": "2026-11-26",
            "asof": "2026-11-26 10:27:03"}
        env = run(ctx, "equity", {"symbol": "600519"})
        snap = env["data"]["data"]["snapshot"]
        assert snap["close"] == 1460.65, "盘中现价覆盖上一收盘"
        assert snap["live"] is True
        assert snap["kline_date"] == "2026-11-26"
        assert env["as_of"] == "2026-11-26"

    def test_overview_live_same_day_not_flagged(self, ctx):
        """live 日期与快照同日 = 同一份数据：不覆盖、不标 live——休市时
        live 就是最近收盘，把它标成「实时」是冒充。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "symbol": "600519", "name": "贵州茅台", "close": 1474.84,
            "percent": 0.0102, "kline_date": "2026-11-26"}
        ctx.fetcher._override["kline.query_last_live"] = {
            "symbol": "600519", "close": 999.0, "percent": 0.5,
            "date": "2026-11-26"}
        env = run(ctx, "equity", {"symbol": "600519"})
        snap = env["data"]["data"]["snapshot"]
        assert snap["close"] == 1474.84
        assert "live" not in snap

    def test_overview_live_older_date_never_rolls_back(self, ctx):
        """停牌票：live 停在更早日期 → 不覆盖（现价不能倒回停牌前）。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "symbol": "000001", "name": "平安银行", "close": 12.4,
            "percent": 0.008, "kline_date": "2026-11-26"}
        ctx.fetcher._override["kline.query_last_live"] = {
            "symbol": "000001", "close": 9.9, "percent": -0.2,
            "date": "2026-11-10"}
        env = run(ctx, "equity", {"symbol": "000001"})
        snap = env["data"]["data"]["snapshot"]
        assert snap["close"] == 12.4
        assert "live" not in snap

    def test_overview_live_failure_degrades(self, ctx):
        """盘中快照失败只丢实时（告警 + 收盘快照原样），概览不塌。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "symbol": "600519", "name": "贵州茅台", "close": 1474.84,
            "percent": 0.0102, "kline_date": "2026-11-25"}
        original = ctx.fetcher.call

        def no_live(target, **params):
            if target == "kline.query_last_live":
                raise RuntimeError("boom")
            return original(target, **params)

        ctx.fetcher.call = no_live
        env = run(ctx, "equity", {"symbol": "600519"})
        snap = env["data"]["data"]["snapshot"]
        assert snap["close"] == 1474.84 and "live" not in snap
        assert any("盘中现价读取失败" in w for w in env["warnings"])

    def test_overview_etf_unsupported_is_a_warning(self, ctx):
        """ETF 的 live 上游返回 ``{"ok": false, "message": ...}`` 的 dict
        （**不是异常**，2026-11-26 实测）——转告警如实说明，不冒充有实时。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "symbol": "510300", "name": "沪深300ETF", "close": 4.1,
            "percent": 0.01, "kline_date": "2026-11-25"}
        ctx.fetcher._override["kline.query_last_live"] = {
            "code": "unsupported", "message": "ETF 无分钟线/分时数据源",
            "ok": False, "symbol": "510300"}
        env = run(ctx, "equity", {"symbol": "510300"})
        snap = env["data"]["data"]["snapshot"]
        assert snap["close"] == 4.1 and "live" not in snap
        assert any("无盘中快照" in w for w in env["warnings"])

    def test_overview_does_not_mutate_cached_snapshot(self, ctx):
        """概览合并**不得改写 hub 缓存的原始快照对象**：hub 缓存的是取数
        对象本身（连同首次算好的 as_of），直接改会把第一笔的结果烤进
        后续所有请求——实测第 1 次 as_of=今天、第 2 次起合并跳过、信封
        as_of 退回冻结的旧值。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "symbol": "600519", "name": "贵州茅台", "close": 1474.84,
            "percent": 0.0102, "kline_date": "2026-11-25"}
        ctx.fetcher._override["kline.query_last_live"] = {
            "symbol": "600519", "close": 1460.65, "percent": -0.0096,
            "date": "2026-11-26"}
        first = run(ctx, "equity", {"symbol": "600519"})
        second = run(ctx, "equity", {"symbol": "600519"})
        assert first["as_of"] == "2026-11-26"
        assert second["as_of"] == "2026-11-26", "缓存被改写会让第二次合并失效"
        snap2 = second["data"]["data"]["snapshot"]
        assert snap2["live"] is True and snap2["close"] == 1460.65

    def test_decomp_loads_directly_without_confirm(self, ctx):
        """拆解**不再确认**（2026-11-25 用户拍板）：显式请求直接取数。

        历史口径（免注册池实测）：5 年档热态 1.58 万、10 年档 32.9 万、
        冷态首查 72.2 万 EC——成本提示已按用户要求一并移除。
        """
        env = run(ctx, "equity", {"symbol": "600519", "section": "decomp"})
        assert env["ok"] is True
        assert env["data"].get("needs_confirm") is not True
        assert env["data"]["data"].get("summary"), "直接加载就要有数据"

    def test_decomp_not_flagged_expensive(self, ctx):
        """拆解不再标 expensive——页签上不出现星号、不进确认分支。"""
        env = run(ctx, "equity", {"symbol": "600519"})
        flags = {s["key"]: s["expensive"] for s in env["data"]["sections"]}
        assert flags["decomp"] is False

    def test_confirm_mechanism_structure_kept(self, ctx):
        """确认**机制**保留（通用），当前没有分区会触发。

        直接调确认分支的内部函数，防未来重新启用时退化：
        没有模型时 `known=False`，**绝不写 0**（0 会被读成免费）。
        """
        from workbench.tools.equity.handler import _section_estimate
        est = _section_estimate(ctx, "600519", "decomp", {"years": 10})
        assert "known" in est and "lo" in est and "hi" in est
        if not est["known"]:
            assert est["lo"] is None and est["hi"] is None

    def test_decomp_as_of_is_block_end_date(self, ctx):
        """拆解的信封 as_of = 块内 end_date（拆解区间的真实末日）。

        上游信封 as_of 恒空，此前把块内已有的日期浪费掉了——真实模式
        页顶永远没有「截至」。"""
        env = run(ctx, "equity", {"symbol": "600519", "section": "decomp",
                                  "years": 3, "confirmed": True})
        data = env["data"]["data"]
        assert data.get("end_date"), "演示数据也有拆解末日"
        assert env["as_of"] == data["end_date"]

    def test_years_passed_through_to_upstream(self, ctx):
        """年限参数仍要透传给上游（拆解成本随年限不同）。"""
        seen: list[dict] = []
        original = ctx.fetcher.call

        def spy(target, **params):
            if target == "income.decomp_one":
                seen.append(dict(params))
            return original(target, **params)

        ctx.fetcher.call = spy
        run(ctx, "equity", {"symbol": "600519", "section": "decomp",
                            "years": 10})
        assert seen and seen[0].get("years") == 10

    def test_years_clamped_to_allowed_set(self, ctx):
        """上游只认 3/5/10；传 7 要就近钳到 5（不是报错，也不是原样发出）。"""
        from workbench.tools.equity.decomp import ALLOWED_YEARS, _years
        assert _years({"years": 7}) == 5
        assert _years({"years": 1}) == 3
        assert _years({"years": 99}) == 10
        for want in ALLOWED_YEARS:
            assert _years({"years": want}) == want

    def test_sections_flagged_expensive(self, ctx):
        env = run(ctx, "equity", {"symbol": "600519"})
        flags = {s["key"]: s["expensive"] for s in env["data"]["sections"]}
        assert flags["decomp"] is False, "拆解已去确认（2026-11-25）"
        assert flags["overview"] is False

    def test_valuation_section(self, ctx):
        env = run(ctx, "equity", {"symbol": "600519", "section": "valuation"})
        assert env["ok"] is True
        series = env["data"]["data"]["series"]
        assert "pe_ttm" in series
        dates = [p["date"] for p in series["pe_ttm"]]
        assert dates == sorted(dates), "估值序列必须按日期升序"

    def test_statements_section(self, ctx):
        """财务报表是**跨期透视**：每科目一行、各期一列。

        走公开门面 ``statements.income``（2026-11-25 起脱离内部命名空间），
        返回 ``list[{k,cn,vals{期次:值}}]``，``period`` 回显档位。
        """
        env = run(ctx, "equity", {"symbol": "600519", "section": "statements",
                                  "domain": "income"})
        assert env["ok"] is True
        data = env["data"]["data"]
        assert data["rows"] and data["periods"]
        assert data["sdk_domain"] == "statements.income"
        assert data["period"] == "annual"
        for row in data["rows"]:
            assert row["cn"] and isinstance(row["vals"], dict)

    def test_statements_section_quarter(self, ctx):
        """季报档：期次键为 ``YYYY-Qn``（最近 5 个已披露季报，降序）。"""
        env = run(ctx, "equity", {"symbol": "600519", "section": "statements",
                                  "domain": "income", "period": "quarter"})
        assert env["ok"] is True
        data = env["data"]["data"]
        assert data["period"] == "quarter"
        assert data["periods"] and all("Q" in p for p in data["periods"])
        assert data["periods"] == sorted(data["periods"], reverse=True)

    def test_minute_section_real_shape(self, ctx):
        """分时分区走真实扁平形（bars 升序 t/close + trading_day/
        updated_at 顶层）；空分时给 intraday=false + note，不回退日 K。"""
        ctx.fetcher._override["kline.query_min1_live"] = {
            "bar_n": 2, "market": "cn", "symbol": "600519",
            "trading_day": "2026-11-26",
            "updated_at": "2026-11-26 09:44:20",
            "bars": [
                {"t": "09:31", "hm": "0931", "close": 1462.0},
                {"t": "09:30", "hm": "0930", "close": 1461.0},
            ],
        }
        env = run(ctx, "equity", {"symbol": "600519", "section": "minute"})
        assert env["ok"] is True
        data = env["data"]["data"]
        assert data["intraday"] is True
        ts = [b["t"] for b in data["bars"]]
        assert ts == ["09:30", "09:31"], "分时点必须升序"
        assert data["updated_at"] == "2026-11-26 09:44:20"

    def test_minute_empty_degrades_honestly(self, ctx):
        """空分时（上游无覆盖）→ intraday=false + note；**不回退日 K**——
        用户要的是分时，悄悄换图等于骗点击。"""
        ctx.fetcher._override["kline.query_min1_live"] = {
            "bar_n": 0, "bars": [], "market": "cn", "symbol": "600519",
            "trading_day": "", "updated_at": "",
        }
        env = run(ctx, "equity", {"symbol": "600519", "section": "minute"})
        data = env["data"]["data"]
        assert data["intraday"] is False
        assert data["bars"] == []
        assert data["note"] == "上游无分时覆盖"

    def test_minute_empty_with_trading_day_says_why(self, ctx):
        """上游应答了（有 trading_day）却没点数：note 要说清「未开盘或
        该标的无分钟源（ETF 不供分时，指数用 index. 键）」——一律说
        「未开盘」会把指数/ETF 的入口不匹配伪装成时段问题（2026-11-26
        用户实测撞上）。"""
        ctx.fetcher._override["kline.query_min1_live"] = {
            "bar_n": 0, "bars": [], "market": "cn", "symbol": "510300",
            "trading_day": "2026-11-26", "updated_at": "",
        }
        env = run(ctx, "equity", {"symbol": "510300", "section": "minute"})
        note = env["data"]["data"]["note"]
        assert "未开盘" in note and "ETF" in note and "index." in note

    def test_minute_index_symbol_routes_to_index_entry(self, ctx):
        """指数键在个股分时入口下无数据（返回空 MAP，2026-11-26 实测）
        ——``index.`` 前缀必须显式路由到 ``query_index_min1_live``（与
        个股分时同形；裸码进指数入口只会拿到 None）。"""
        seen: list[str] = []
        original = ctx.fetcher.call

        def spy(target, **params):
            seen.append(target)
            if target == "kline.query_index_min1_live":
                return {"bar_n": 1, "market": "cn", "symbol": "index.hs300",
                        "trading_day": "2026-11-26",
                        "updated_at": "2026-11-26 10:26:52",
                        "bars": [{"t": "09:30", "hm": "0930",
                                  "close": 3916.41,
                                  "volume_delta": 1, "amount_delta": 1}]}
            return original(target, **params)

        ctx.fetcher.call = spy
        env = run(ctx, "equity", {"symbol": "index.hs300",
                                  "section": "minute"})
        assert env["ok"] is True
        data = env["data"]["data"]
        assert data["intraday"] is True and data["bars"]
        assert "kline.query_index_min1_live" in seen
        assert "kline.query_min1_live" not in seen

    def test_minute_avg_from_cum_fields(self, ctx):
        """均价线=当日成交均价：上游分时无均价字段（按「先查已有指标」
        确认），自算 = 累计 amount ÷ 累计 volume（VWAP；volume 已是股）。
        数据口径 2026-11-26 实测：volume/amount=当日累计、*_delta=当分钟。"""
        ctx.fetcher._override["kline.query_min1_live"] = {
            "bar_n": 2, "market": "cn", "symbol": "600519",
            "trading_day": "2026-11-26", "updated_at": "2026-11-26 10:58:58",
            "bars": [
                {"t": "09:30", "hm": "0930", "close": 10.0,
                 "volume": 100000.0, "amount": 1005000.0},
                {"t": "09:31", "hm": "0931", "close": 10.2,
                 "volume": 200000.0, "amount": 2030000.0},
            ],
        }
        env = run(ctx, "equity", {"symbol": "600519", "section": "minute"})
        bars = env["data"]["data"]["bars"]
        assert bars[0]["avg"] == 10.05, "累计额/累计量"
        assert abs(bars[1]["avg"] - 10.15) < 1e-6, "均价随累计滚动"

    def test_minute_avg_skipped_for_index(self, ctx):
        """指数分时不算均价：指数 volume 是成分股聚合量纲（不以手披露、
        不满足 ×close≈amount），累计额÷累计量不是价格——画出来是造假。"""
        ctx.fetcher._override["kline.query_index_min1_live"] = {
            "bar_n": 1, "market": "cn", "symbol": "index.hs300",
            "trading_day": "2026-11-26", "updated_at": "2026-11-26 10:58:58",
            "bars": [{"t": "09:30", "hm": "0930", "close": 3916.41,
                      "volume": 6212812.0, "amount": 14043386878.0}],
        }
        env = run(ctx, "equity", {"symbol": "index.hs300",
                                  "section": "minute"})
        bar = env["data"]["data"]["bars"][0]
        assert "avg" not in bar

    def test_minute_avg_dropped_when_units_insane(self, ctx):
        """量纲破损防护：均价超出现价 [1/3, 3] 倍（日 VWAP 与收盘价同在
        日内区间，正常到不了这量级）→ 丢弃不画——画出一条错线比不画更
        骗人。"""
        ctx.fetcher._override["kline.query_min1_live"] = {
            "bar_n": 1, "market": "cn", "symbol": "600519",
            "trading_day": "2026-11-26", "updated_at": "",
            "bars": [{"t": "09:30", "hm": "0930", "close": 10.0,
                      "volume": 1000.0, "amount": 5.0e7}],
        }
        env = run(ctx, "equity", {"symbol": "600519", "section": "minute"})
        assert "avg" not in env["data"]["data"]["bars"][0]

    def test_minute_force_bypasses_hub_cache(self, ctx):
        """``force`` 透传：默认 30s TTL 内第二次请求走缓存（不发上游），
        force=True 绕过——「刷新」按钮要的是此刻的数据。"""
        env1 = run(ctx, "equity", {"symbol": "600519", "section": "minute"})
        calls_after_first = len(ctx.fetcher.calls)
        run(ctx, "equity", {"symbol": "600519", "section": "minute"})
        assert len(ctx.fetcher.calls) == calls_after_first, "TTL 内应命中缓存"
        run(ctx, "equity", {"symbol": "600519", "section": "minute",
                            "force": True})
        assert len(ctx.fetcher.calls) > calls_after_first, "force 必须直取上游"

    def test_bars_section(self, ctx):
        """「行情走势」：升序 K 线 + as_of 取**最新一根**。

        真实 ``kline.query_bars`` 返回是新→旧，``as_of_of`` 取原始列表
        ``[-1]`` 会把最旧一天当数据截至日——handler 必须用归一后的最后一行覆盖。
        """
        env = run(ctx, "equity", {"symbol": "600519", "section": "bars",
                                  "days": 40})
        envelope_ok(env)
        assert env["ok"] is True
        data = env["data"]["data"]
        bars = data["bars"]
        assert bars and data["count"] == len(bars)
        dates = [b["date"] for b in bars]
        assert dates == sorted(dates), "K 线必须按日期升序给前端"
        for b in bars:
            assert {"date", "open", "high", "low", "close"} <= set(b)
            assert "sas" not in b, "上游数据集标识不透传给用户"
        assert env["as_of"] == dates[-1]

    def test_bars_days_clamped(self, ctx):
        """days 钳 20–500：越界不是错误，是用户的粗略意图。"""
        env = run(ctx, "equity", {"symbol": "600519", "section": "bars",
                                  "days": 9999})
        assert env["data"]["data"]["days"] == 500
        env = run(ctx, "equity", {"symbol": "600519", "section": "bars",
                                  "days": 1})
        assert env["data"]["data"]["days"] == 20

    def test_bars_empty_raises_readable(self, ctx):
        """空数据必须是可读错误，不是渲染一张空表。"""
        ctx.fetcher._override["kline.query_bars"] = []
        env = run(ctx, "equity", {"symbol": "600519", "section": "bars"})
        assert env["ok"] is False
        assert env["meta"]["code"] == "upstream"

    def test_bars_skipped_rows_disclosed(self, ctx):
        """缺 OHLC 的行丢弃但计数——不画假实体，也不静默。"""
        ctx.fetcher._override["kline.query_bars"] = [
            {"date": "2026-11-20", "open": 1, "high": 2, "low": 0.5,
             "close": 1.5, "volume": 10},
            {"date": "2026-11-19"},  # 整行缺 OHLC
        ]
        env = run(ctx, "equity", {"symbol": "600519", "section": "bars"})
        data = env["data"]["data"]
        assert [b["date"] for b in data["bars"]] == ["2026-11-20"]
        assert any("1 行" in w for w in env["warnings"])

    def test_unknown_section(self, ctx):
        env = run(ctx, "equity", {"symbol": "600519", "section": "nope"})
        assert env["ok"] is False

    def test_missing_symbol(self, ctx):
        env = run(ctx, "equity", {})
        assert env["ok"] is False
        assert env["meta"]["code"] == "missing_param"


# --------------------------------------------------------------------------
# 持仓账本
# --------------------------------------------------------------------------

def _trades() -> list[dict]:
    return [
        {"date": "2025-01-02", "code": "600519", "side": "buy",
         "shares": 100, "price": 1288.4},
        {"date": "2025-03-02", "code": "600519", "side": "buy",
         "shares": 100, "price": 1435.2},
        {"date": "2025-06-02", "code": "600519", "side": "sell",
         "shares": 100, "price": 1502.0},
        {"date": "2025-02-02", "code": "000001", "side": "buy",
         "shares": 1000, "price": 10.5},
    ]


class TestPortfolio:
    def test_pricing_as_of_from_snapshots(self, ctx):
        """定价截止日来自快照的 kline_date：信封 as_of = max，
        载荷给 min/max（停牌票定价停在更早日期时如实显示区间）。"""
        env = run(ctx, "portfolio", {"trades": _trades()})
        assert env["ok"] is True
        data = env["data"]
        assert data["priced_as_of"] == env["as_of"]
        assert data["price_date_min"] <= data["price_date_max"]
        assert data["priced_as_of"] == data["price_date_max"]

    def test_pricing_as_of_empty_when_nothing_priced(self, ctx):
        """全部缺价时三个定价日期键如实为空——**不编、不写 0**。"""
        ctx.fetcher._override["kline.snapshot"] = {}
        env = run(ctx, "portfolio", {"trades": _trades()})
        assert env["ok"] is True
        data = env["data"]
        assert data["priced_as_of"] == ""
        assert data["price_date_min"] == ""
        assert data["price_date_max"] == ""

    def test_pricing_accepts_batchresult_wrapper(self, ctx):
        """真实批量 ``kline.snapshot``（sym 列表）返回 **BatchResult**
        （快照表在 ``.results`` 属性）而非 dict——2026-11-25 真实模式实测。
        此前 isinstance(raw, dict) 判空导致真实模式持仓全部缺价，
        旧夹具 dict 全绿——「演示全绿、真实才崩」的又一例（D-25 同类）。"""

        class FakeBatchResult:
            """只模拟真实对象与本 handler 相关的部分。"""

            def __init__(self, results):
                self.results = results

        ctx.fetcher._override["kline.snapshot"] = FakeBatchResult({
            "600519": {"close": 1462.38, "kline_date": "2026-11-25"},
            "000001": {"close": 11.86, "kline_date": "2026-11-10"},
        })
        env = run(ctx, "portfolio", {"trades": _trades()})
        assert env["ok"] is True
        data = env["data"]
        assert data["totals"]["valued"] == data["totals"]["total"], (
            "BatchResult 形状下所有标的都应取到价")
        assert data["price_date_min"] == "2026-11-10"
        assert data["priced_as_of"] == "2026-11-25"
        assert env["as_of"] == "2026-11-25"

    def test_rows_carry_name_from_pricing_snapshot(self, ctx):
        """行表带名称——23 字段定价快照自带 ``name``，是已取回数据的免费
        透出（不发任何额外请求）；名称缺失回落「—」，不拿代码冒充。"""
        ctx.fetcher._override["kline.snapshot"] = {
            "600519": {"close": 1462.38, "name": "贵州茅台",
                       "kline_date": "2026-11-25"},
            "000001": {"close": 11.86, "kline_date": "2026-11-25"},
        }
        env = run(ctx, "portfolio", {"trades": _trades()})
        rows = {r["code"]: r for r in env["data"]["rows"]}
        assert rows["600519"]["name"] == "贵州茅台"
        assert rows["000001"]["name"] == "—", "快照无名称时回落「—」"
        before = len(ctx.fetcher.calls)
        run(ctx, "portfolio", {"trades": _trades()})
        assert len(ctx.fetcher.calls) - before <= 1, "名称不增加任何请求"

    def test_five_methods_give_different_realized(self, ctx):
        """五法结果必须互不相同——退化成同一法会红。"""
        env = run(ctx, "portfolio", {"trades": _trades(), "method": "FIFO"})
        envelope_ok(env)
        assert env["ok"] is True
        realized = {}
        for item in env["data"]["by_method"]:
            if "error" in item:
                continue
            realized[item["method"]] = round(item["realized"] or 0.0, 4)
        assert realized["FIFO"] != realized["LIFO"], realized
        assert realized["FIFO"] != realized["AVERAGE"], realized
        assert "SPECIFIC" not in realized, "未指定 lot_id 时 SPECIFIC 应报错"

    def test_single_batch_price_request(self, ctx):
        """定价一次批量，不逐票。"""
        before = len(ctx.fetcher.calls)
        run(ctx, "portfolio", {"trades": _trades()})
        price_calls = [c for c in ctx.fetcher.calls[before:]
                       if c[0] == "kline.snapshot"]
        assert len(price_calls) == 1

    def test_totals_mark_completeness(self, ctx):
        env = run(ctx, "portfolio", {"trades": _trades()})
        totals = env["data"]["totals"]
        assert totals["valued"] == totals["total"]
        assert totals["complete"] is True

    def test_missing_price_excluded_from_total(self, ctx):
        """缺价标的**不计入合计**，且 ``valued < total``。

        把缺价当 0 会让组合市值凭空少一只票，而合计数字看起来完全正常。
        """
        original = ctx.fetcher.call

        def no_price(target, **params):
            if target == "kline.snapshot":
                return {}
            return original(target, **params)

        ctx.fetcher.call = no_price
        env = run(ctx, "portfolio", {"trades": _trades()})
        totals = env["data"]["totals"]
        assert totals["valued"] == 0
        assert totals["total"] == 2
        assert totals["complete"] is False
        assert totals["value"] is None, "一行都没价时合计应为缺失，不是 0"
        assert env["warnings"]

    def test_realized_counted_after_full_liquidation(self, ctx):
        """清仓标的的已实现盈亏必须计入组合合计（不能从总额里消失）。"""
        trades = [
            {"date": "2025-01-02", "code": "600519", "side": "buy",
             "shares": 100, "price": 1000.0},
            {"date": "2025-02-02", "code": "600519", "side": "sell",
             "shares": 100, "price": 1200.0},
        ]
        env = run(ctx, "portfolio", {"trades": trades})
        assert env["data"]["rows"] == [], "清仓后不该有持仓行"
        assert env["data"]["totals"]["realized"] == pytest.approx(20000.0)

    def test_oversell_rejected(self, ctx):
        trades = [
            {"date": "2025-01-02", "code": "600519", "side": "buy",
             "shares": 100, "price": 1000.0},
            {"date": "2025-02-02", "code": "600519", "side": "sell",
             "shares": 200, "price": 1200.0},
        ]
        env = run(ctx, "portfolio", {"trades": trades})
        assert env["ok"] is False
        assert env["meta"]["code"] == "insufficient_shares"

    def test_bad_method(self, ctx):
        env = run(ctx, "portfolio", {"trades": _trades(), "method": "XYZ"})
        assert env["ok"] is False

    def test_save_then_list(self, ctx):
        run(ctx, "portfolio", {"action": "save", "name": "主账户",
                               "trades": _trades()})
        env = run(ctx, "portfolio", {"action": "list"})
        assert "主账户" in env["data"]["sets"]

    def test_twr_block(self, ctx):
        nav = [{"date": "2025-01-01", "nav": 100.0},
               {"date": "2025-01-02", "nav": 110.0}]
        env = run(ctx, "portfolio", {"trades": _trades(), "nav": nav})
        assert env["data"]["twr"]["total"] == pytest.approx(0.10)

    def test_var_block(self, ctx):
        returns = [-0.05, -0.02, 0.0, 0.01, 0.02]
        env = run(ctx, "portfolio", {"trades": _trades(), "returns": returns})
        assert env["data"]["var"]["var"] == pytest.approx(0.05)

    def test_missing_trades(self, ctx):
        env = run(ctx, "portfolio", {})
        assert env["ok"] is False
        assert env["meta"]["code"] == "missing_param"

    def test_bad_json_trades(self, ctx):
        env = run(ctx, "portfolio", {"trades": "{not json"})
        assert env["ok"] is False
        assert env["meta"]["action"] == "fix_input"

    def test_trade_missing_field_names_the_row(self, ctx):
        """缺字段要指出「第几笔」，不能只说「参数错误」。"""
        env = run(ctx, "portfolio", {"trades": [
            {"date": "2025-01-02", "code": "600519", "side": "buy",
             "shares": 100, "price": 1000.0},
            {"date": "2025-01-03", "code": "600519", "side": "buy",
             "price": 1000.0},
        ]})
        assert env["ok"] is False
        assert "第 2 笔" in env["meta"]["error"]


# --------------------------------------------------------------------------
# EC 试算
# --------------------------------------------------------------------------

class TestEcEstimate:
    def test_no_model_returns_none_not_zero(self, ctx):
        """无成本模型 → ``pred_*`` 为 ``None``，**不是 0**。

        0 会被读成「免费」，而这个错误让用户在最贵的操作上毫无防备。
        """
        env = run(ctx, "ec_estimate", {"target": "screener.query"})
        envelope_ok(env)
        assert env["ok"] is True
        est = env["data"]["estimate"]
        assert est["pred_lo"] is None
        assert est["pred_hi"] is None
        assert est["model"] == "unavailable"

    def test_unknown_target_rejected(self, ctx):
        before = len(ctx.fetcher.calls)
        env = run(ctx, "ec_estimate", {"target": "kline.query_bars"})
        assert env["ok"] is False
        assert len(ctx.fetcher.calls) == before

    def test_over_budget_flagged(self, ctx):
        ctx.fetcher.cost_estimate = lambda t, **p: {
            "ec_lo": 100_000, "ec_hi": 500_000, "model": "test"}
        env = run(ctx, "ec_estimate", {"target": "dividend.decomp"})
        assert env["data"]["over_budget"] is True
        assert env["data"]["estimate"]["pred_hi"] == 500_000

    def test_message_explains_unknown(self, ctx):
        env = run(ctx, "ec_estimate", {"target": "screener.query"})
        assert "未知" in env["data"]["message"]


# --------------------------------------------------------------------------
# 凭证热切
# --------------------------------------------------------------------------

class TestKey:
    def test_probe_unsupported_never_writes(self, ctx):
        """取数器不支持热切（测试替身/未接入态）→ 探针判失败，
        **不写任何凭证**——「没有探针能力就默认成功」是绝对禁止的。"""
        env = run(ctx, "key", {"client_id": "abc", "client_secret": "def"})
        envelope_ok(env)
        assert env["ok"] is False
        assert env["meta"]["code"] == "probe_failed"
        assert ctx.store.get_credentials() is None

    def test_probe_failure_keeps_old(self, ctx, tmp_path):
        """探针失败不替换凭证、不清缓存。"""
        from workbench.bootstrap import build_context as bc
        from workbench.client.fetchers import WmshareFetcher

        real = bc(store=Store(tmp_path / "r.db"),
                  env={"WMSHARE_CLIENT_ID": "old_id",
                       "WMSHARE_CLIENT_SECRET": "old_secret"})
        assert isinstance(real.fetcher, WmshareFetcher)
        # 未装凭证校验前先塞一个已知 client，便于断言「没被换掉」
        sentinel = object()
        real.fetcher._client = sentinel
        env = real.registry["key"](real, {"client_id": "new",
                                          "client_secret": "new"})
        assert env["ok"] is False
        assert env["meta"]["code"] == "probe_failed"
        assert real.fetcher._client is sentinel, "探针失败不该替换 client"

    def test_never_echoes_secret(self, ctx, tmp_path):
        """响应只给尾 4 位，绝不回显 secret。"""
        from workbench.bootstrap import build_context as bc

        real = bc(store=Store(tmp_path / "r2.db"),
                  env={"WMSHARE_CLIENT_ID": "cid1234",
                       "WMSHARE_CLIENT_SECRET": "verysecret"})
        real.fetcher.rekey = lambda *a, **kw: True    # 假装探针通过
        env = real.registry["key"](real, {"client_id": "cid1234",
                                          "client_secret": "verysecret"})
        blob = json.dumps(env, ensure_ascii=False)
        assert "verysecret" not in blob
        assert env["data"]["client_id_tail"] == "1234"

    def test_missing_fields(self, ctx):
        from workbench.bootstrap import build_context as bc

        real = bc(store=Store(ctx.store.path.parent / "r3.db"),
                  env={"WMSHARE_CLIENT_ID": "a", "WMSHARE_CLIENT_SECRET": "b"})
        env = real.registry["key"](real, {"client_id": "only"})
        assert env["ok"] is False
        assert env["meta"]["code"] == "missing_param"


# --------------------------------------------------------------------------
# 工具注册表与端点一致性
# --------------------------------------------------------------------------

class TestRegistry:
    def test_all_endpoints_have_handlers(self, ctx):
        """契约里的每个端点都必须有 handler（否则前端拿到 501 空态）。"""
        from workbench.core.envelope import ENDPOINTS

        assert set(ctx.registry) == set(ENDPOINTS)

    def test_tools_endpoint_marks_all_ready(self, ctx):
        env = run(ctx, "tools", {})
        not_ready = [t["slug"] for t in env["data"]["tools"] if not t["ready"]]
        assert not not_ready, f"未实现的工具：{not_ready}"

    def test_every_handler_returns_envelope(self, ctx):
        """遍历全部端点：每个都必须返回合规信封，且不抛异常。"""
        from workbench.core.envelope import ENDPOINTS

        for slug in ENDPOINTS:
            env = run(ctx, slug, {})
            envelope_ok(env)


class TestWatchlistDegradation:
    """批量接口被策略拒时逐票降级（免注册的真实行为）。

    实测：批量快照在免注册下返回 ``403 POLICY_DENIED / 不允许调用
    memo.cacheset``，而**单票** ``kline.snapshot`` 可用（免注册边界表，
    2026-11-24）。不降级的话，没配凭证的用户打开自选页会直接失败——
    而真数据本可取到。新旧入口同名（都是 ``kline.snapshot``），按参数
    形状区分：列表 = 批量、字符串 = 单票。
    """

    class _Denied(Exception):
        """模拟 SDK 的 AuthError（含 POLICY_DENIED 文案）。"""

        def __init__(self):
            super().__init__(
                "免注册访问被拒绝（HTTP 403，POLICY_DENIED）：策略拒绝："
                "不允许调用 memo.cacheset")
            self.__class__.__name__ = "AuthError"

    def test_falls_back_to_per_symbol(self, ctx):
        original = ctx.fetcher.call

        def deny_batch(target, **params):
            # 只拒批量（sym 是列表）；单票（字符串）放行——与免注册真实
            # 边界一致
            if (target == "kline.snapshot"
                    and isinstance(params.get("sym"), list)):
                raise self._Denied()
            return original(target, **params)

        ctx.fetcher.call = deny_batch
        env = run(ctx, "watchlist", {"symbols": "600519,000001"})
        assert env["ok"] is True
        data = env["data"]
        assert data["degraded"] is True
        assert data["source"] == "kline.snapshot"
        assert data["request_count"] == 2, "降级后请求数应等于标的数"
        assert data["count"] == 2
        # 降级原因必须让用户看见
        assert env["warnings"], "降级必须给 warning"
        assert "逐票" in env["warnings"][0]
        assert "2 次请求" in env["warnings"][0]

    def test_no_degradation_when_batch_works(self, ctx):
        env = run(ctx, "watchlist", {"symbols": "600519,000001"})
        data = env["data"]
        assert data["degraded"] is False
        assert data["request_count"] == 2, "批量快照 + 日期伴取共 2 次"
        assert env["warnings"] == []

    def test_non_auth_errors_do_not_degrade(self, ctx):
        """网络/限流类错误**不**降级——否则 1 个失败放大成 N 个。"""
        def boom(target, **params):
            raise TimeoutError("network timeout")

        ctx.fetcher.call = boom
        env = run(ctx, "watchlist", {"symbols": "600519"})
        assert env["ok"] is False, "非权限错误应整体失败，而不是逐票重试"

    def test_degraded_as_of_is_max_row_date_not_first_ticket(self, ctx):
        """降级路径的 as_of 此前只留第一只成功票的日期——其余票的
        kline_date 被丢弃。改为各行 max（数据事实）。"""
        original = ctx.fetcher.call

        def deny_batch(target, **params):
            if (target == "kline.snapshot"
                    and isinstance(params.get("sym"), list)):
                raise self._Denied()
            return original(target, **params)

        ctx.fetcher.call = deny_batch
        env = run(ctx, "watchlist", {"symbols": "600519,000001"})
        rows = env["data"]["rows"]
        assert all(r.get("kline_date") for r in rows)
        assert env["as_of"] == max(r["kline_date"] for r in rows)

    def test_single_symbol_failure_kept_as_row(self, ctx):
        original = ctx.fetcher.call

        def flaky(target, **params):
            if (target == "kline.snapshot"
                    and isinstance(params.get("sym"), list)):
                raise self._Denied()
            if params.get("sym") == "000001":
                raise RuntimeError("boom")
            return original(target, **params)

        ctx.fetcher.call = flaky
        env = run(ctx, "watchlist", {"symbols": "600519,000001"})
        rows = {r["symbol"]: r for r in env["data"]["rows"]}
        assert rows["000001"]["missing"] is True
        assert rows["600519"].get("missing") is None
        assert "1 只取数失败" in env["warnings"][0]

    def test_empty_watchlist_is_not_filled(self, ctx):
        """空清单返回空表，不自动塞示例标的（那会让人以为配过）。"""
        env = run(ctx, "watchlist", {"symbols": ""})
        # 显式空串 → 走默认示例（这是「打开就有东西看」的设计）
        assert env["data"]["count"] > 0


class TestWatchlistWrite:
    """自选增删：**零取数**写本地库。

    此前的缺口：`store.add_watch/remove_watch` 早已实现却无任何调用方，
    用户只能读到 `DEFAULT_SYMBOLS` 那 5 只样例——「自选存在本地库」这句话
    在文档里写了很久，但没有写入路径。
    """

    def test_add_writes_and_echoes_saved(self, ctx):
        env = ctx.registry["watchlist"](ctx, {"action": "add",
                                             "symbol": "000858"})
        assert env["ok"] is True, env["meta"]
        assert env["data"]["saved"] == ["000858"]

    def test_add_is_idempotent(self, ctx):
        """重复加入不报错也不产生重复行（`INSERT OR IGNORE`）。"""
        for _ in range(3):
            env = ctx.registry["watchlist"](ctx, {"action": "add",
                                                  "symbol": "000858"})
        assert env["data"]["saved"] == ["000858"]

    def test_remove_deletes(self, ctx):
        ctx.registry["watchlist"](ctx, {"action": "add", "symbol": "000858"})
        env = ctx.registry["watchlist"](ctx, {"action": "remove",
                                             "symbol": "000858"})
        assert env["data"]["saved"] == []

    def test_write_makes_zero_upstream_requests(self, ctx):
        """写入**零取数**——它只碰本地库。

        这条是关键：如果哪天有人「顺便刷新一下行情」，用户每加一只票
        就多一次上游请求，而 UI 上看不出来。
        """
        before = len(ctx.fetcher.calls)
        ctx.registry["watchlist"](ctx, {"action": "add", "symbol": "000858"})
        assert len(ctx.fetcher.calls) == before, "写入不该发任何上游请求"

    def test_saved_list_is_read_back(self, ctx):
        """再查行情时读的是**库里**的清单，不是样例清单。"""
        ctx.registry["watchlist"](ctx, {"action": "add", "symbol": "000858"})
        env = ctx.registry["watchlist"](ctx, {})
        assert "000858" in env["data"]["symbols"]

    def test_missing_symbol_rejected(self, ctx):
        env = ctx.registry["watchlist"](ctx, {"action": "add"})
        assert env["ok"] is False
        assert env["meta"]["code"] == "missing_param"

    def test_unknown_action_rejected(self, ctx):
        env = ctx.registry["watchlist"](ctx, {"action": "nope"})
        assert env["ok"] is False
        assert env["meta"]["code"] == "param"


class TestPortfolioArchive:
    """持仓档案 save / list / load。

    **`load` 是补上的缺口**：此前只有 `save` 与 `list`，存进去的成交只
    出现在档案名列表里，拿不回具体内容——只能存不能续。
    """

    TRADES = ('[{"date":"2026-01-05","code":"600519","side":"buy",'
              '"shares":100,"price":1400}]')

    def test_save_then_load_roundtrip(self, ctx):
        ctx.registry["portfolio"](ctx, {"action": "save", "name": "主仓",
                                       "trades": self.TRADES})
        env = ctx.registry["portfolio"](ctx, {"action": "load", "name": "主仓"})
        assert env["ok"] is True, env["meta"]
        assert env["data"]["n_trades"] == 1
        assert env["data"]["trades"][0]["code"] == "600519"

    def test_list_shows_saved_name(self, ctx):
        ctx.registry["portfolio"](ctx, {"action": "save", "name": "主仓",
                                       "trades": self.TRADES})
        env = ctx.registry["portfolio"](ctx, {"action": "list"})
        assert "主仓" in env["data"]["sets"]

    def test_load_missing_name_is_readable_error(self, ctx):
        env = ctx.registry["portfolio"](ctx, {"action": "load",
                                             "name": "不存在"})
        assert env["ok"] is False
        assert env["meta"]["code"] == "param"
        assert "不存在" in env["meta"]["error"]

    def test_load_requires_name(self, ctx):
        env = ctx.registry["portfolio"](ctx, {"action": "load"})
        assert env["ok"] is False
        assert env["meta"]["code"] == "missing_param"

    def test_archive_actions_make_zero_requests(self, ctx):
        """save/list/load 全是本地库操作，零上游请求。"""
        ctx.registry["portfolio"](ctx, {"action": "save", "name": "x",
                                       "trades": self.TRADES})
        before = len(ctx.fetcher.calls)
        ctx.registry["portfolio"](ctx, {"action": "list"})
        ctx.registry["portfolio"](ctx, {"action": "load", "name": "x"})
        assert len(ctx.fetcher.calls) == before


# --------------------------------------------------------------------------
# 数据源（新鲜度参照日）
# --------------------------------------------------------------------------

class TestSourcesReference:
    def test_reference_date_is_disclosed(self, ctx):
        """age_days 是相对数，必须把参照日一并给出——夹具=锚点日，
        真实=今天。没有锚点的相对新鲜度用户无从校验。"""
        env = run(ctx, "sources", {})
        envelope_ok(env)
        assert env["ok"] is True
        reference = env["data"]["reference"]
        assert len(reference) == 10 and reference[4] == "-"
        assert env["meta"]["reference"] == reference
