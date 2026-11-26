"""真实模式契约：**目录函数 vs 组合门面**必须走对路径。

这一组用例来自一次真实的配置错误：整个项目在演示模式下十页全绿，
一配真实凭证就大面积失败。原因有两类，且**演示模式完全掩盖了它们**：

1. ``screener.query`` / ``backtest.run`` / ``screener.index_*`` 是**组合门面**，
   不在 wmshare 目录里。``client.call()`` 会抛 ``CatalogError: 未知函数``；
   必须走 ``client.<ns>.<method>()``。
2. ``kline.index_breadth_summary`` 等目录函数要求显式 ``idx``，门面则用
   ``LatestIndexKey()`` 自行解析。调错路径会得到「缺少必填参数」。

演示模式不走真实 SDK，所以这两类错误都不会暴露——这正是为什么需要
**离线断言「走的是哪条路径」**，而不是只断言「返回了数据」。
"""

from __future__ import annotations

import pytest
from shape_data import shape_for
from workbench.bootstrap import build_context
from workbench.client.fetchers import FakeFetcher
from workbench.platform.store import Store


@pytest.fixture()
def ctx(tmp_path):
    return build_context(fetcher=FakeFetcher(resolver=shape_for),
                         store=Store(tmp_path / "t.db"))


class TestFacadeRouting:
    """组合门面必须经 ``fetcher.facade()``，不得经 ``fetcher.call()``。"""

    #: 这些 target 是门面名，目录里不存在。
    FACADE_TARGETS = {
        "screener.query": ("screener", "query"),
        "backtest.run": ("backtest", "run"),
        "screener.index_breadth_summary": ("screener", "index_breadth_summary"),
        "screener.index_breadth_bins": ("screener", "index_breadth_bins"),
        "screener.index_top_movers": ("screener", "index_top_movers"),
        "index.trend": ("index", "trend"),
        "kline.bars": ("kline", "bars"),
    }

    def test_screener_uses_facade(self, ctx):
        ctx.registry["screener"](ctx, {"where": "$PE_TTM < 15", "limit": 3})
        targets = [t for t, _ in ctx.fetcher.calls]
        assert "screener.query" in targets

    def test_backtest_uses_facade(self, ctx):
        ctx.registry["backtest"](ctx, {"symbol": "600519",
                                       "begin": "2025-01-01",
                                       "end": "2026-11-20"})
        assert "backtest.run" in [t for t, _ in ctx.fetcher.calls]

    def test_equity_bars_uses_catalog_call(self, ctx):
        """``kline.query_bars`` 在目录里（2026-11-25 实测），必须走
        ``call()``；新取数点先断言路径，是本文件存在的理由。"""
        ctx.registry["equity"](ctx, {"symbol": "600519", "section": "bars"})
        assert "kline.query_bars" in [t for t, _ in ctx.fetcher.calls]

    def test_backtest_price_bars_use_facade(self, ctx):
        """回测页的价格 K 线走 ``cli.kline.bars`` 门面（目录里没有
        ``kline.bars``），不得用 ``call()``。"""
        seen: list[tuple[str, str]] = []
        original = ctx.fetcher.facade

        def spy(ns, method, **params):
            seen.append((ns, method))
            return original(ns, method, **params)

        ctx.fetcher.facade = spy
        ctx.registry["backtest"](ctx, {"symbol": "600519",
                                       "begin": "2025-01-01",
                                       "end": "2026-11-20"})
        assert ("kline", "bars") in seen

    def test_markets_uses_facade_for_breadth(self, ctx):
        ctx.registry["markets"](ctx, {})
        targets = [t for t, _ in ctx.fetcher.calls]
        for name in ("screener.index_breadth_summary",
                     "screener.index_breadth_bins",
                     "screener.index_top_movers"):
            assert name in targets, f"{name} 未走门面"

    def test_dashboard_uses_facade_for_breadth(self, ctx):
        ctx.registry["dashboard"](ctx, {})
        assert "screener.index_breadth_summary" in [t for t, _ in ctx.fetcher.calls]

    def test_dashboard_valuation_uses_trend_facade(self, ctx):
        """驾驶舱 PE/PB 走 ``cli.index.trend`` 门面（目录里没有
        ``index.trend``，``cli.call`` 会抛 CatalogError——2026-11-25 实测）；
        ``indices.valuation`` 只承担股息率与季度回退口径。"""
        seen: list[tuple[str, str]] = []
        original = ctx.fetcher.facade

        def spy(ns, method, **params):
            seen.append((ns, method))
            return original(ns, method, **params)

        ctx.fetcher.facade = spy
        ctx.registry["dashboard"](ctx, {})
        assert ("index", "trend") in seen

    def test_live_targets_are_catalog_calls(self, ctx):
        """实时四取数点都在目录里（call() 直达）：自选盘中伴取
        ``kline.query_last_live_many``、概览盘中现价
        ``kline.query_last_live``、个股分时 ``kline.query_min1_live``、
        指数盘中 ``kline.query_index_last_live_many``（参数名 keys）。"""
        ctx.registry["watchlist"](ctx, {"symbols": "600519", "live": True})
        ctx.registry["equity"](ctx, {"symbol": "600519", "section": "minute"})
        ctx.registry["equity"](ctx, {"symbol": "600519"})
        ctx.registry["dashboard"](ctx, {})
        targets = [t for t, _ in ctx.fetcher.calls]
        for name in ("kline.query_last_live_many",
                     "kline.query_last_live",
                     "kline.query_min1_live",
                     "kline.query_index_last_live_many"):
            assert name in targets, f"{name} 未走目录调用"
        keys_params = [p for t, p in ctx.fetcher.calls
                       if t == "kline.query_index_last_live_many"]
        assert keys_params and keys_params[0].get("keys"), \
            "指数盘中的参数名是 keys（syms 会 UsageError）"

    def test_index_minute_routes_to_index_entry(self, ctx):
        """指数分时必须显式选入口：``index.`` 前缀走
        ``kline.query_index_min1_live``（上游不自动改写路由——裸码进
        个股入口拿空 MAP、进指数入口拿 None，都查不到数）。"""
        ctx.registry["equity"](ctx, {"symbol": "index.hs300",
                                     "section": "minute"})
        calls = [p for t, p in ctx.fetcher.calls
                 if t == "kline.query_index_min1_live"]
        assert calls and calls[0].get("key") == "index.hs300"

    def test_watchlist_batch_is_snapshot_catalog_call(self, ctx):
        """自选列走目录函数 ``kline.snapshot``（``sym`` 传列表自动路由
        批量，23 字段含名称与区间指标）；live_many 只作日期伴取（快照
        批量路由不物化 kline_date）。旧逐票入口 ``kline.query_last``
        （9 字段 bar）已退场。"""
        ctx.registry["watchlist"](ctx, {"symbols": "600519,000001"})
        batched = [p for t, p in ctx.fetcher.calls
                   if t == "kline.snapshot"]
        assert batched and isinstance(batched[0].get("sym"), list)
        dated = [p for t, p in ctx.fetcher.calls
                 if t == "kline.query_last_live_many"]
        assert dated and isinstance(dated[0].get("syms"), list)
        assert all(t != "kline.query_last" for t, _ in ctx.fetcher.calls)

    def test_no_handler_calls_catalog_name_for_facade(self, ctx):
        """反向断言：**不得**出现用 ``call()`` 调门面名的情况。

        用 ``facade()`` 与 ``call()`` 在演示态下都能拿到数据（FakeFetcher
        两者都实现），所以只断言「有数据」抓不到错。这里断言调用形态。
        """
        seen: list[tuple[str, str]] = []

        def spy_call(target, **params):
            seen.append(("call", target))
            return demo(target, params)

        def spy_facade(ns, method, **params):
            seen.append(("facade", f"{ns}.{method}"))
            return demo(f"{ns}.{method}", params)

        from shape_data import shape_for as demo

        ctx.fetcher.call = spy_call
        ctx.fetcher.facade = spy_facade

        for slug, body in (("screener", {"where": "$PE_TTM < 15"}),
                           ("backtest", {"symbol": "600519",
                                         "begin": "2025-01-01",
                                         "end": "2026-11-20"}),
                           ("dashboard", {}),
                           ("markets", {})):
            ctx.registry[slug](ctx, body)

        facade_names = {t for kind, t in seen if kind == "facade"}
        called_names = {t for kind, t in seen if kind == "call"}
        for name in self.FACADE_TARGETS:
            assert name not in called_names, f"{name} 被当成目录函数调用"
        assert facade_names & set(self.FACADE_TARGETS), "没有任何门面走 facade()"


class TestShapeNormalization:
    """门面可能返回 DataFrame，handler 必须归一成 JSON 友好结构。

    **归一只有一份实现**（`tools/_shared.as_records`）。此前 markets /
    equity.dividend / equity.indicators / equity.statements 各写一遍，
    四份语义还有差别——同一个坑修四次、漏一次就复发。
    """

    def test_dataframe_is_normalized_to_records(self):
        """``to_dict("records")`` 鸭子类型 —— 不 import pandas。"""
        from workbench.tools._shared import as_records

        class FakeFrame:
            def to_dict(self, orient):
                assert orient == "records"
                return [{"bin": "涨", "count": 3}]

        assert as_records(FakeFrame()) == [{"bin": "涨", "count": 3}]

    def test_list_passthrough(self):
        from workbench.tools._shared import as_records
        assert as_records([{"a": 1}, {"a": 2}]) == [{"a": 1}, {"a": 2}]

    def test_none_and_scalars_become_empty(self):
        from workbench.tools._shared import as_records
        assert as_records(None) == []
        assert as_records(42) == []

    def test_single_dict_becomes_one_row(self):
        """单个 dict 是**一行**，不是「没有」。

        返回空列表会让调用方把「有一行」当成「没有」——`forecast.snapshot`
        的每一块都是单 dict，这里若返回 [] 整块就消失了。
        """
        from workbench.tools._shared import as_records
        assert as_records({"k": "roe", "vals": {"2025": 0.3}}) == [
            {"k": "roe", "vals": {"2025": 0.3}}]

    def test_no_tool_reimplements_normalization(self):
        """**防复发**：不得在工具层再写一份 ``_as_records``。

        这是棘轮式断言——只要有人重新复制一遍归一逻辑就会红。
        `_as_statement_rows` / `_as_rows` 允许存在，但它们做的是**业务过滤**
        （必须含跨期 `vals`），形状归一必须调 `as_records`。
        """
        import pathlib
        import re

        root = (pathlib.Path(__file__).resolve().parents[1]
                / "backend" / "workbench" / "tools")
        offenders: list[str] = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^def _as_records\(", text, re.M):
                offenders.append(f"{path.name}::_as_records")
        assert not offenders, f"归一逻辑被重复实现：{offenders}"

    def test_markets_survives_dataframe_payload(self, ctx):
        """门面返回 DataFrame 时型页不应白屏。"""
        class FakeFrame:
            def to_dict(self, orient):
                return [{"symbol": "600519", "name": "贵州茅台", "percent": 0.01,
                         "net_mf": 1e8}]

        original = ctx.fetcher.facade

        def frame_facade(ns, method, **params):
            if method == "index_top_movers":
                return FakeFrame()
            return original(ns, method, **params)

        ctx.fetcher.facade = frame_facade
        env = ctx.registry["markets"](ctx, {})
        assert env["ok"] is True
        assert env["data"]["movers"], "DataFrame 未被归一成 movers 行"


class TestAuthErrorClassification:
    def test_policy_denied_maps_to_config(self):
        """免注册被拒 → ``config``（用户要做的动作是配凭证）。"""

        class AuthError(Exception):
            pass

        from workbench.tools._shared import classify_exc
        action, code = classify_exc(AuthError("POLICY_DENIED"))
        assert action == "config"
        assert code == "autherror"


class TestStatementDomainMapping:
    """四张表全部走 `statements.*` **公开门面**，不碰内部命名空间。

    历史：三表曾走内部目录函数（UI 简称 vs `fin.*` 全名两套命名，传简称
    得到「不在允许值」）。2026-11-25 起改走 `cli.statements.*` 门面
    （原生支持 `period='annual'|'quarter'`），UI 简称 → 门面方法名显式映射。
    """

    EXPECTED = {
        "income": "income",
        "balance": "balance",
        "cashflow": "cashflow",
    }

    def test_mapping_is_complete(self):
        from workbench.tools.equity.statements import STATEMENT_DOMAINS
        assert STATEMENT_DOMAINS == self.EXPECTED

    @pytest.mark.parametrize("kind,method", list(EXPECTED.items()))
    def test_handler_sends_facade_with_period(self, ctx, kind, method):
        """必须走 `fetcher.facade('statements', method)` 且带 period 参数。"""
        seen: list[tuple[str, str, dict]] = []
        original = ctx.fetcher.facade

        def spy(ns, m, **params):
            seen.append((ns, m, params))
            return original(ns, m, **params)

        ctx.fetcher.facade = spy
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "statements",
                                           "domain": kind,
                                           "period": "quarter"})
        assert env["ok"] is True
        hit = [s for s in seen if s[1] == method]
        assert hit, f"未走 statements.{method}：{seen}"
        assert hit[0][0] == "statements"
        assert hit[0][2]["period"] == "quarter", hit
        assert env["data"]["data"]["sdk_domain"] == f"statements.{method}"
        assert env["data"]["data"]["period"] == "quarter"

    def test_short_name_rejected_locally(self, ctx):
        """传内部全名本身（而不是简称）→ 本地拒绝，不发请求。"""
        before = len(ctx.fetcher.calls)
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "statements",
                                           "domain": "fin.income_statement"})
        assert env["ok"] is False
        assert env["meta"]["code"] == "param"
        assert len(ctx.fetcher.calls) == before, "参数非法时不该发请求"

    def test_period_quarter_gives_quarter_keys(self, ctx):
        """季报档期次键是 ``YYYY-Qn``（与真实 indicators(period='quarter')
        实测同形），且是最近 5 个已披露季报。"""
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "statements",
                                           "domain": "income",
                                           "period": "quarter"})
        periods = env["data"]["data"]["periods"]
        assert periods and all("Q" in p for p in periods), periods
        assert periods == sorted(periods, reverse=True)

    def test_shape_is_periods_and_rows(self, ctx):
        """返回 `periods` + `rows[{k,cn,vals}]`，不是 `items[{key,value,yoy}]`。

        真实 `rptdom.statement` 是**跨期透视**（每科目一行、各期一列）。
        旧 handler 假定单期 `items`，演示数据也照那个捏——两处都错。
        """
        # 三表（科目明细）与指标表（主要指标）行结构不同：
        #   科目表：{k, cn, vals}
        #   指标表：{k, label, format, vals}
        # 两者共用 periods + rows 的外层结构。
        for kind, name_key in (("income", "cn"), ("indicators", "label")):
            env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                               "section": "statements",
                                               "domain": kind})
            data = env["data"]["data"]
            assert "periods" in data and "rows" in data, kind
            assert data["periods"], f"{kind} 期次列不能为空"
            assert data["periods"] == sorted(data["periods"], reverse=True), \
                f"{kind} 期次应降序（最近一期在前）"
            for row in data["rows"]:
                assert {"k", name_key, "vals"} <= set(row), (kind, row)
                assert isinstance(row["vals"], dict)

    def test_shape_fixture_matches_real(self):
        """**演示数据必须与真实同构** —— 否则演示能跑、真机就崩。"""
        from shape_data import SHAPE_DATA

        rows = SHAPE_DATA["statements.income"]
        assert isinstance(rows, list), "真实返回是 list，演示也必须是 list"
        assert rows
        for row in rows:
            assert "k" in row and "cn" in row
            assert isinstance(row.get("vals"), dict) and row["vals"]
            # 值是跨期字典（期次 → 数值），不是单个标量
            assert all(isinstance(v, (int, float)) for v in row["vals"].values())


class TestDividendSection:
    """分红：`bonus.snapshot` 一个接口给全 18 字段，**不要分开调单项接口**。

    踩过的错：用 `bonus.snapshot_yield_ttm` 取 TTM 股息率——它返回的是
    **裸 float**（0.0354），按 dict 处理得到 `{}`，页面显示「—」。
    用户会以为「这只票没有分红数据」，而数据完全可用。
    """

    def test_uses_bonus_snapshot_not_scalar_endpoint(self, ctx):
        sent: list[str] = []
        original = ctx.fetcher.call

        def spy(target, **params):
            sent.append(target)
            return original(target, **params)

        ctx.fetcher.call = spy
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "dividend"})
        assert env["ok"] is True
        assert "bonus.snapshot" in sent, f"未用 bonus.snapshot：{sent}"
        assert "bonus.snapshot_yield_ttm" not in sent, \
            "该接口返回裸 float，按 dict 处理会静默丢数据"

    def test_fields_cover_key_metrics(self, ctx):
        """TTM 股息率/派息率/每股分红/3 年统计都要在。"""
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "dividend"})
        keys = {f["key"] for f in env["data"]["data"]["dividend_fields"]}
        for need in ("yield_ttm", "payout_ttm", "dps_ttm",
                     "yield_3y_avg", "yield_3y_min"):
            assert need in keys, f"缺 {need}"

    def test_each_field_declares_format(self, ctx):
        """口径由后端声明（pct/money/num/text），前端不自己猜。"""
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "dividend"})
        for f in env["data"]["data"]["dividend_fields"]:
            assert f["format"] in ("pct", "money", "num", "text"), f
            assert f["label"], f

    def test_trend_is_localized(self, ctx):
        """上游英文枚举不得直接显示给用户。"""
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "dividend"})
        trend = next((f for f in env["data"]["data"]["dividend_fields"]
                      if f["key"] == "yield_3y_trend"), None)
        if trend is not None:
            assert trend["value"] not in ("valley", "peak", "flat"), trend

    def test_history_sorted_desc(self, ctx):
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "dividend"})
        dates = [h["announce"] or "" for h in
                 env["data"]["data"]["dividend_history"]]
        assert dates == sorted(dates, reverse=True), "公告日应降序（最近在前）"

    def test_does_not_collide_with_valuation_fields(self, ctx):
        """键名不能叫 `fields` —— 估值分区已占用该键（string[]）。

        同一分区集里两个 `fields` 指两种东西，前端必读错。
        """
        env_v = ctx.registry["equity"](ctx, {"symbol": "600519",
                                             "section": "valuation"})
        env_d = ctx.registry["equity"](ctx, {"symbol": "600519",
                                             "section": "dividend"})
        assert isinstance(env_v["data"]["data"].get("fields"), list)
        assert "dividend_fields" in env_d["data"]["data"]
        assert "fields" not in env_d["data"]["data"]


class TestStatementKinds:
    """三张表都要能取 —— 早期只接了利润表，用户以为「只有利润表」。"""

    KINDS = ("income", "balance", "cashflow")

    @pytest.mark.parametrize("kind", KINDS)
    def test_each_kind_returns_rows(self, ctx, kind):
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "statements",
                                           "domain": kind})
        assert env["ok"] is True, env["meta"]
        data = env["data"]["data"]
        assert data["rows"], f"{kind} 无科目"
        assert data["periods"], f"{kind} 无期次"

    def test_each_kind_sends_its_own_domain(self, ctx):
        """三个 kind 发出的门面方法必须各不相同。

        只断言「都有行」是不够的：如果 handler 忽略 domain 参数、永远发
        income，三张表都能渲染出数据，用户却以为自己在看资产负债表。
        """
        sent: list[str] = []
        original = ctx.fetcher.facade

        def spy(ns, method, **params):
            if ns == "statements":
                sent.append(method)
            return original(ns, method, **params)

        ctx.fetcher.facade = spy
        for kind in self.KINDS:
            ctx.registry["equity"](ctx, {"symbol": "600519",
                                         "section": "statements",
                                         "domain": kind})
        assert len(set(sent)) == 3, f"三个 kind 只发出 {set(sent)}"


class TestIndicatorSheet:
    """主要指标表：走**门面** `cli.statements.indicators`，不是目录函数。

    `rptdom.statement` 的 `domain` 只接受三张会计表全名
    （`fin.balance_sheet` / `fin.income_statement` / `fin.cashflow_statement`），
    **不含** `fin.indicator*`——传进去得到「不在允许值」。指标表在 SDK 里
    由门面 `build_statement_xs` + `eval_result` 组合，必须走 facade。

    另外上游客 `cn` 是 `k` 的副本（`basicEps` 之类），不是中文名，
    所以中文名必须自己维护映射表。
    """

    def test_uses_facade_not_catalog(self, ctx):
        seen: list[str] = []
        original_facade = ctx.fetcher.facade

        def spy(ns, method, **params):
            seen.append(f"{ns}.{method}")
            return original_facade(ns, method, **params)

        ctx.fetcher.facade = spy
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "statements",
                                           "domain": "indicators"})
        assert env["ok"] is True, env["meta"]
        assert "statements.indicators" in seen, seen

    def test_default_statement_view_is_indicators(self, ctx):
        """不传 domain 时默认给主要指标 —— 不是利润表明细。

        默认落在 52 行科目明细上等于让用户自己在几百个数字里找重点。
        """
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "statements"})
        data = env["data"]["data"]
        keys = {r["k"] for r in data["rows"]}
        assert "roe" in keys or "totalOperatingIncome" in keys, \
            f"默认视图不是主要指标：{sorted(keys)[:5]}"

    def test_primary_indicators_ordered_first(self, ctx):
        """主要指标要排在前面（按分析阅读顺序），其余跟在后面。"""
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "statements",
                                           "domain": "indicators"})
        data = env["data"]["data"]
        primary = data["primary"]
        got = [r["k"] for r in data["rows"]]
        head = got[:len(primary)]
        assert head == list(primary), f"主指标未置前：{head}"

    def test_labels_are_chinese_not_key_copies(self, ctx):
        """上游 `cn` 是 key 副本，必须自己映射中文名。"""
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "statements",
                                           "domain": "indicators"})
        rows = {r["k"]: r for r in env["data"]["data"]["rows"]}
        assert rows["roe"]["label"] == "净资产收益率 ROE"
        assert rows["grossProfitRatio"]["label"] == "毛利率"
        for r in rows.values():
            assert r["label"] != r["k"], f"{r['k']} 没有中文名"

    def test_each_indicator_declares_format(self, ctx):
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "statements",
                                           "domain": "indicators"})
        for r in env["data"]["data"]["rows"]:
            assert r["format"] in ("money", "pct", "num", "days"), r

    def test_unknown_indicator_keeps_key(self):
        """未登记的指标原样保留 key —— 不猜中文名（猜错比英文更难发现）。"""
        from workbench.tools.equity.indicators import _label
        out = _label({"k": "someUnknownKey", "vals": {"2025": 1.0}})
        assert out["label"] == "someUnknownKey"
        assert out["format"] == "num"


class TestForecastSection:
    """业绩预告：`forecast.snapshot` 一个接口给三块。

    **上游的 0 是「没披露」不是「零」**（实测 601318 的 2015 半年报预告：
    `np_lower=0` 而同行的 `np_amp_lower=0.62` 是真值）。原样显示会造出
    「预计净利润 0 元 ～ 0 元」这条上游从未给出的事实。
    """

    def test_uses_snapshot_not_single_purpose_targets(self, ctx):
        """必须走 `forecast.snapshot`，不要分开调三个单项接口。

        分三次调会在某块缺失时让「没有」与「调错了」变得无法区分。
        """
        seen: list[str] = []
        original = ctx.fetcher.call

        def spy(target, **params):
            seen.append(target)
            return original(target, **params)

        ctx.fetcher.call = spy
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "forecast"})
        assert env["ok"] is True, env["meta"]
        assert seen == ["forecast.snapshot"], seen

    def test_all_three_blocks_present(self, ctx):
        """三块都要出现，**包括空块**。

        只渲染有数据的那块会让用户以为「这页只有快报」，而实际上这家
        公司根本没发过预告——「没发」和「没显示」是两件事。
        """
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "forecast"})
        blocks = env["data"]["data"]["forecast_blocks"]
        assert [b["key"] for b in blocks] == [
            "yjyg", "yjkb", "next_disclosure"]

    def test_zero_becomes_none_not_zero(self, ctx):
        """0 归一成 None —— 页面显示「—」，不是「0 元」。

        演示数据故意保留上游的 `deduct_lower=0`，让这条归一逻辑在演示态
        也真的被执行到。
        """
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "forecast"})
        blocks = {b["key"]: b for b in env["data"]["data"]["forecast_blocks"]}
        fields = {f["key"]: f for f in blocks["yjyg"]["fields"]}
        assert fields["deduct_lower"]["value"] is None
        assert fields["deduct_upper"]["value"] is None
        # 非零的真值必须留着
        assert fields["np_lower"]["value"] == 6.92e10

    def test_zero_helper_does_not_eat_none_or_strings(self):
        from workbench.tools.equity.forecast import _is_zero
        assert _is_zero(0) is True
        assert _is_zero(0.0) is True
        assert _is_zero(None) is False
        assert _is_zero("0") is False
        assert _is_zero(False) is False

    def test_stale_forecast_is_flagged(self, ctx):
        """两年前的「最新预告」要标出来，不能当当前预期展示。

        实测：茅台的最近预告报告期 2024-12-31（公告 2025-01-03），
        年报预告只在跨年发一次，「最新」不一定是「近期」。
        """
        import shape_data as demo_data

        old = demo_data._RESHAPERS["forecast.snapshot"]({"sym": "600519"})
        old["yjyg"]["report_date"] = "2024-12-31"
        original = demo_data._RESHAPERS["forecast.snapshot"]
        demo_data._RESHAPERS["forecast.snapshot"] = lambda p: old
        try:
            env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                               "section": "forecast"})
        finally:
            demo_data._RESHAPERS["forecast.snapshot"] = original

        data = env["data"]["data"]
        assert data["yjyg_stale"] is True
        assert data["yjyg_age_days"] > 400
        assert any("最新" in w for w in env["warnings"]), env["warnings"]

    def test_age_uses_data_as_of_not_wall_clock(self, ctx):
        """陈旧天数相对**数据截至日**算，不相对系统当天。

        用 wall clock 会让演示态（固定快照）凭空多出天数，而且同一页面
        隔几天再看数字会变——那不是数据在变，是参照系在漂。
        """
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "forecast"})
        age = env["data"]["data"]["yjyg_age_days"]
        # 演示快照的报告期 2025-12-31，数据截至 2026-11-20 → 324 天
        assert age == 324, f"年龄应按数据截至日算，得到 {age}"


class TestDecompSection:
    """持有收益拆解：直接加载（2026-11-25 用户拍板去确认）+ `ok=false` 是有效结果。"""

    def test_loads_directly_without_confirm(self, ctx):
        """不再弹确认框：显式请求即直接取数（成本提示已按用户要求移除）。"""
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "decomp"})
        assert env["ok"] is True, env["meta"]
        assert env["data"].get("needs_confirm") is not True
        assert "summary" in env["data"]["data"]

    def test_call_hits_decomp_one(self, ctx):
        seen: list[str] = []
        original = ctx.fetcher.call

        def spy(target, **params):
            seen.append(target)
            return original(target, **params)

        ctx.fetcher.call = spy
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "decomp"})
        assert env["ok"] is True, env["meta"]
        assert "income.decomp_one" in seen, seen

    def test_sum_identity_holds(self, ctx):
        """`价格 + 股息 = 总收益` 必须成立。

        股息贡献是后复权 − 不复权的差值（含再投），所以这个恒等式
        天然成立；演示数据也要满足它——否则用户会先怀疑我们的加法。
        """
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "decomp", "years": 5})
        vals = {f["key"]: f["value"] for f in env["data"]["data"]["summary"]}
        assert abs(vals["price_return"] + vals["dividend_return"]
                   - vals["total_return"]) < 1e-9

    def test_ok_false_is_shown_not_raised(self, ctx):
        """次新股 `ok=false` 要如实显示原因，**不当成接口故障**。

        上游只返回 `{ok:false, reason}`，没有任何收益字段。抛成错误会让
        用户去查网络，而问题在于这只票上市太晚。
        """
        env = ctx.registry["equity"](ctx, {"symbol": "300750",
                                           "section": "decomp",
                                           "confirmed": True, "years": 3})
        assert env["ok"] is True, "ok=false 不该变成失败信封"
        data = env["data"]["data"]
        assert data["ok"] is False
        assert "K 线覆盖不足" in data["reason"]
        assert any("无法拆解" in w for w in env["warnings"])

    def test_default_years_is_five_not_ten(self):
        """默认取 5 不取 10：10 年档实测可达 33 万 EC。

        默认值不该是最贵的那个档位——那等于每次都替用户做了一次昂贵选择。
        """
        from workbench.tools.equity.decomp import DEFAULT_YEARS
        assert DEFAULT_YEARS == 5

    def test_yearly_and_monthly_sorted_ascending(self, ctx):
        env = ctx.registry["equity"](ctx, {"symbol": "600519",
                                           "section": "decomp",
                                           "confirmed": True, "years": 5})
        data = env["data"]["data"]
        years = [r["year"] for r in data["yearly"]]
        assert years == sorted(years), "逐年表要升序"
        dates = [m["date"] for m in data["monthly"]]
        assert dates == sorted(dates), "月末序列要升序"

    def test_dividend_label_is_contribution_not_yield(self):
        """标签是「股息贡献」不是「股息率」。

        它是后复权与不复权的差值（含再投效应），写成股息率会被读成
        当期收益率，而两者含义完全不同。
        """
        from workbench.tools.equity.decomp import SUMMARY_FIELDS
        labels = {k: label for k, label, _ in SUMMARY_FIELDS}
        assert labels["dividend_return"] == "股息贡献"


class TestCostMessageHonesty:
    """确认框的「成本可见」不得低于实测——模型上界偏低必须补一句。

    实测（2026-11-25）：`income.decomp_one` 的 SDK 成本模型 `ec_hi=200,000`，
    而真实观测到单票尖刺 721,953 EC。只在框里写 20 万、实际扣 72 万，
    是「成本可见」原则的破口。
    """

    def test_warns_when_model_upper_bound_below_measured(self):
        from workbench.tools.equity import decomp
        msg = decomp.cost_message(
            {"known": True, "lo": 8000, "hi": 200_000, "model": "measured",
             "measured_peak": 721_953}, "收益拆解")
        assert "721,953" in msg, msg
        assert "模型上界低于实测" in msg, msg

    def test_no_warning_when_model_covers_measured(self):
        """模型上界已经够高时**不要**再喊狼来了——噪声会让警告失效。"""
        from workbench.tools.equity import decomp
        msg = decomp.cost_message(
            {"known": True, "lo": 8000, "hi": 900_000, "model": "measured",
             "measured_peak": 721_953}, "收益拆解")
        assert "模型上界低于实测" not in msg, msg

    def test_unknown_model_still_states_measured_peak(self):
        """无模型时也不能只说「无法预估」——实测峰值是已知事实。"""
        from workbench.tools.equity import decomp
        msg = decomp.cost_message(
            {"known": False, "measured_peak": 721_953}, "收益拆解")
        assert "721,953" in msg, msg
