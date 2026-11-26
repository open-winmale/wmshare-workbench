"""访问方式判定：`凭证 / 免注册 / 未接入` 三态，**没有任何一态给假数据**。

**为什么这条必须有**：曾经的设计把「没配凭证」等同于「演示」（内置假快照），
于是装了 wmshare 的用户直接启动会看到一屏假数字——而
``Client.from_env()`` 在凭证双缺时本就能免注册真实取数。
假数字和真数字长得一模一样，用户无从分辨。demo 模式已整体移除：
现在「未接入」态的任何取数都以可分类异常失败，绝不返回长得像真数据的空壳。

已实测（wmshare 4.2.0）：免注册 client 的 ``auth_mode == "public_pool"``，
``kline.query_last`` 返回真实数据，``cost_estimate`` 也正常。
"""

from __future__ import annotations

from workbench.client.fetchers import (
    FakeFetcher,
    MissingFetcher,
    NotReadyError,
    WmshareFetcher,
    resolve_auth_mode,
)


class TestResolveAuthMode:
    def test_no_credentials_with_wmshare_is_public_pool(self, monkeypatch):
        """**核心**：装了 wmshare、没凭证 → 免注册（真实数据），不是假数据。

        这条是当初语义修复的主断言。若退化成「给假数据」，用户会拿到假数字。
        """
        monkeypatch.setattr("workbench.client.fetchers.wmshare_installed",
                            lambda: True)
        monkeypatch.delenv("WMSHARE_DISABLE_ANON", raising=False)
        assert resolve_auth_mode(has_credentials=False) == "public_pool"

    def test_with_credentials_is_credentials(self, monkeypatch):
        monkeypatch.setattr("workbench.client.fetchers.wmshare_installed",
                            lambda: True)
        assert resolve_auth_mode(has_credentials=True) == "credentials"

    def test_no_wmshare_is_missing(self, monkeypatch):
        """未装 SDK → 未接入态（要给出原因与补救指引，不给假数据）。"""
        monkeypatch.setattr("workbench.client.fetchers.wmshare_installed",
                            lambda: False)
        assert resolve_auth_mode(has_credentials=False) == "missing"

    def test_anon_disabled_is_missing(self, monkeypatch):
        """``WMSHARE_DISABLE_ANON=1`` + 无凭证 → 未接入（不假装能取数）。"""
        monkeypatch.setattr("workbench.client.fetchers.wmshare_installed",
                            lambda: True)
        monkeypatch.setenv("WMSHARE_DISABLE_ANON", "1")
        assert resolve_auth_mode(has_credentials=False) == "missing"


class TestFetcherFlags:
    def test_fake_fetcher_is_not_real(self):
        f = FakeFetcher()
        assert f.real is False
        assert f.auth_mode == "fake"
        # 未注入且无 resolver：宁可响亮失败，也不静默给假数据
        try:
            f.call("kline.query_bars")
        except KeyError:
            pass
        else:
            raise AssertionError("未注入的 target 必须 KeyError，不能静默给数据")

    def test_missing_fetcher_fails_with_classifiable_error(self):
        """未接入态的取数请求抛 ``NotReadyError``（→ action=config）。"""
        f = MissingFetcher(reason="未安装 wmshare")
        try:
            f.call("kline.query_bars")
        except NotReadyError as exc:
            assert "kline.query_bars" in str(exc)
            assert "未安装 wmshare" in str(exc)
        else:
            raise AssertionError("未接入态取数必须 NotReadyError")

    def test_missing_fetcher_facade_also_fails(self):
        f = MissingFetcher()
        try:
            f.facade("screener", "query")
        except NotReadyError:
            pass
        else:
            raise AssertionError("门面调用同样必须失败")

    def test_wmshare_fetcher_is_real(self):
        assert WmshareFetcher({"client_id": "a", "client_secret": "b"}).real is True

    def test_wmshare_fetcher_without_credentials_is_public_pool(self):
        """无凭证的 WmshareFetcher 仍是真实取数器（免注册）。"""
        f = WmshareFetcher({})
        assert f.real is True
        assert f.auth_mode == "public_pool"

    def test_wmshare_fetcher_with_credentials(self):
        f = WmshareFetcher({"client_id": "a", "client_secret": "b"})
        assert f.auth_mode == "credentials"


class TestAppInfoExposesMode:
    """`/api/appinfo` 必须把三态暴露给前端（页顶据此显示）。"""

    def _ctx(self, tmp_path, *, monkeypatch, installed: bool):
        from workbench.bootstrap import build_context
        from workbench.platform.store import Store

        monkeypatch.setattr("workbench.client.fetchers.wmshare_installed",
                            lambda: installed)
        monkeypatch.delenv("WMSHARE_DISABLE_ANON", raising=False)
        return build_context(store=Store(tmp_path / "t.db"),
                             env={}, cred_path=tmp_path / "none.env")

    def test_missing_mode_reports_reason(self, tmp_path, monkeypatch):
        ctx = self._ctx(tmp_path, monkeypatch=monkeypatch, installed=False)
        assert isinstance(ctx.fetcher, MissingFetcher)
        assert ctx.mode_reason, "未接入态必须给出原因"
        env = ctx.registry["appinfo"](ctx, {})
        data = env["data"]
        assert data["auth_mode"] == "missing"
        assert data["real"] is False
        # 原因必填——只说「未接入」不告诉用户为什么，等于没解释
        assert "wmshare" in data["reason"] or "pip" in data["reason"]

    def test_public_pool_mode_is_real(self, tmp_path, monkeypatch):
        """无凭证 + 装了 SDK → appinfo 显示免注册且 real=True。"""
        ctx = self._ctx(tmp_path, monkeypatch=monkeypatch, installed=True)
        env = ctx.registry["appinfo"](ctx, {})
        data = env["data"]
        assert data["auth_mode"] == "public_pool", data
        assert data["real"] is True
        assert data["reason"] == ""
        assert isinstance(ctx.fetcher, WmshareFetcher)

    def test_mode_labels_are_distinct(self):
        from workbench.tools.appinfo.handler import MODE_LABELS
        assert len(set(MODE_LABELS.values())) == 3


class TestInjectedFetcher:
    """``build_context(fetcher=...)`` 是测试注入点（零网络零配额）。"""

    def test_injected_fetcher_skips_mode_resolution(self, tmp_path):
        from workbench.bootstrap import build_context
        from workbench.platform.store import Store

        ctx = build_context(store=Store(tmp_path / "i.db"),
                            fetcher=FakeFetcher())
        assert isinstance(ctx.fetcher, FakeFetcher)
        assert ctx.auth_mode == "fake"
        assert ctx.mode_reason == ""


def test_no_handler_reads_fetcher_mode_flag():
    """handler 不得自己判断「是什么访问方式」。

    统一由 ``appinfo`` 回答——各处自己判断正是
    「假的看起来像真的」这类错误的温床。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "backend" / "workbench" / "tools"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "fetcher, \"demo\"" in text or "fetcher.demo" in text \
                or "fetcher.auth_mode" in text:
            offenders.append(path.name + " @ " + path.parent.name)
    assert not offenders, f"这些 handler 自己判断了访问方式：{offenders}"
