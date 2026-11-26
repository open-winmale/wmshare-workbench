"""P2 平台层测试：store / credentials / fetchers / server。

**零网络、零凭证、零真实 ``wmshare.Client``**——这是 ``PROJECT_SPEC`` §6 的离线铁律。
服务端用真实 socket 但只绑回环，且只跑在本进程内起停。
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from workbench.client.fetchers import (
    FakeFetcher,
    build_fetcher,
)
from workbench.platform import credentials as creds
from workbench.platform.server import HOST, ServerContext, serve
from workbench.platform.store import TABLES, Store

# ================================================================ store

@pytest.fixture()
def store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def test_store_creates_nine_tables(store: Store) -> None:
    """九张业务表齐全（另有 schema_meta 记录版本）。"""
    assert set(TABLES) <= set(store.tables())


def test_store_file_permissions_are_0600(store: Store) -> None:
    """库文件 0600——里面有明文凭证。"""
    assert store.permission_ok is True
    assert (store.path.stat().st_mode & 0o777) == 0o600


def test_store_schema_version(store: Store) -> None:
    assert store.version() >= 1


def test_store_credentials_roundtrip(store: Store) -> None:
    assert store.get_credentials() is None       # 无记录 ≠ 空记录
    store.set_credentials("cid", "sec", "cn")
    got = store.get_credentials()
    assert got == {"client_id": "cid", "client_secret": "sec", "market": "cn"}
    store.clear_credentials()
    assert store.get_credentials() is None


def test_store_concurrent_writes_no_lock_error(store: Store) -> None:
    """20 线程并发写不出 ``database is locked``（P2-01 的验收条件）。"""
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            store.add_watch(f"60{i:04d}")
            store.save_hub_state(f"market:quote:{i}", {"v": i},
                                 as_of="2026-11-25", fetched_at=float(i))
        except BaseException as exc:  # noqa: BLE001 - 收集后统一断言
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == []
    assert len(store.list_watch()) == 20


def test_store_snapshot_roundtrip(store: Store) -> None:
    sid = store.add_snapshot(tool="dashboard", payload={"a": 1},
                             as_of="2026-11-25", n_rows=1)
    assert sid > 0
    latest = store.latest_snapshot("dashboard")
    assert latest is not None
    assert latest["payload"] == {"a": 1}


def test_store_position_set_upsert(store: Store) -> None:
    store.save_position_set("主仓", [{"code": "600519", "shares": 100}])
    store.save_position_set("主仓", [{"code": "600519", "shares": 200}])
    assert store.get_position_set("主仓") == [{"code": "600519", "shares": 200}]
    assert store.list_position_sets() == ["主仓"]


def test_store_screen_save_and_list(store: Store) -> None:
    store.save_screen("高股息", "$BONUS_RATE_3Y_AVG_LAST > 0.03",
                      order="$ROE_TTM_LAST")
    got = store.get_screen("高股息")
    assert got is not None
    assert got["where_expr"].startswith("$BONUS_RATE")
    assert len(store.list_screens()) == 1


def test_store_watch_unique_per_group(store: Store) -> None:
    """同一代码同一分组只存一条（重复添加是幂等的）。"""
    store.add_watch("600519")
    store.add_watch("600519")
    store.add_watch("600519", group="bank")
    assert len(store.list_watch()) == 2
    store.remove_watch("600519")
    assert len(store.list_watch()) == 1


def test_store_judgement_log(store: Store) -> None:
    store.add_judgement("600519", "当时认为分红可持续", as_of="2026-11-25")
    rows = store.list_judgements("600519")
    assert len(rows) == 1
    assert "可持续" in rows[0]["note"]


def test_store_hub_state_survives_reopen(tmp_path: Path) -> None:
    """hub 落盘后重开仍在——这就是「重启后仍有 last-known-good」。"""
    p = tmp_path / "t.db"
    s1 = Store(p)
    s1.save_hub_state("market:kline:600519", {"close": 1700},
                      as_of="2026-11-25", fetched_at=1.0)
    s1.close()

    s2 = Store(p)
    rows = s2.load_hub_state()
    s2.close()
    assert len(rows) == 1
    assert rows[0]["value"] == {"close": 1700}


def test_store_ec_ledger_today(store: Store) -> None:
    store.add_ec_ledger("screener.query", pred_lo=70, pred_hi=1000, actual=219)
    store.add_ec_ledger("kline.bars", pred_lo=60, pred_hi=75)   # 无 actual
    today = store.ec_today()
    assert today["calls"] == 2
    assert today["ec_total"] == 219        # 只累加 actual，不把预估值当消耗


# ================================================================ credentials

def test_credentials_file_parse(tmp_path: Path) -> None:
    p = tmp_path / "c.env"
    p.write_text('# comment\nexport WMSHARE_CLIENT_ID="abc"\n'
                 "WMSHARE_CLIENT_SECRET='def'\n", encoding="utf-8")
    data = creds.read_credentials_file(p)
    assert data["WMSHARE_CLIENT_ID"] == "abc"
    assert data["WMSHARE_CLIENT_SECRET"] == "def"


def test_credentials_missing_file_is_empty(tmp_path: Path) -> None:
    assert creds.read_credentials_file(tmp_path / "nope.env") == {}


def test_credentials_write_is_atomic_and_0600(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "c.env"
    creds.write_credentials_file("id1", "sec1", path=p)
    assert p.is_file()
    assert (p.stat().st_mode & 0o777) == 0o600
    assert creds.read_credentials_file(p)["WMSHARE_CLIENT_ID"] == "id1"


def test_credentials_priority_store_beats_env(tmp_path: Path, store: Store) -> None:
    """本库 > env：用户在页面上刚粘贴的 Key 不能被旧环境变量盖掉。"""
    store.set_credentials("store-id", "store-sec")
    r = creds.resolve(store, env={"WMSHARE_CLIENT_ID": "env-id",
                                  "WMSHARE_CLIENT_SECRET": "env-sec"},
                      cred_path=tmp_path / "nope.env")
    assert r.source == "store"
    assert r.client_id == "store-id"


def test_credentials_priority_env_beats_file(tmp_path: Path, store: Store) -> None:
    p = tmp_path / "c.env"
    creds.write_credentials_file("file-id", "file-sec", path=p)
    r = creds.resolve(store, env={"WMSHARE_CLIENT_ID": "env-id",
                                  "WMSHARE_CLIENT_SECRET": "env-sec"},
                      cred_path=p)
    assert r.source == "env"


def test_credentials_falls_back_to_file(tmp_path: Path, store: Store) -> None:
    p = tmp_path / "c.env"
    creds.write_credentials_file("file-id", "file-sec", path=p)
    r = creds.resolve(store, env={}, cred_path=p)
    assert r.source == "file"
    assert r.client_id == "file-id"


def test_credentials_half_pair_is_not_configured(tmp_path: Path, store: Store) -> None:
    """只有 id 没有 secret 视为未配置——SDK 对半套凭证会抛 AuthError。"""
    r = creds.resolve(store, env={"WMSHARE_CLIENT_ID": "only-id"},
                      cred_path=tmp_path / "nope.env")
    assert r.present is False
    assert r.source == "none"


def test_credentials_redacted_never_leaks_secret(tmp_path: Path, store: Store) -> None:
    """``/api/appinfo`` 用它——绝不能出现 secret 原文。"""
    r = creds.ResolvedCredentials("abcdefghij", "SUPER-SECRET-VALUE", source="store")
    out = r.redacted()
    assert "SUPER-SECRET-VALUE" not in json.dumps(out, ensure_ascii=False)
    assert out["client_id_tail"] == "ghij"


# ================================================================ fetchers

def test_fake_fetcher_never_touches_network() -> None:
    """FakeFetcher 只记录调用，不发请求（``calls`` 供「零请求」断言用）。"""
    f = FakeFetcher(data={"kline.query_bars": []})
    f.call("kline.query_bars", sym="600519")
    assert f.calls == [("kline.query_bars", {"sym": "600519"})]
    assert f.real is False
    assert f.auth_mode == "fake"


def test_fake_fetcher_cost_has_no_model() -> None:
    """测试替身不伪造成本：返回 None 而非 0。"""
    est = FakeFetcher().cost_estimate("screener.query")
    assert est["ec_lo"] is None
    assert est["ec_hi"] is None


def test_build_fetcher_missing_mode_gives_missing() -> None:
    """``mode="missing"`` → MissingFetcher（未接入态，任何取数可分类失败）。"""
    f = build_fetcher(None, mode="missing")
    assert f.real is False
    assert f.auth_mode == "missing"


def test_build_fetcher_public_pool_is_real() -> None:
    """**无凭证但装了 SDK 走免注册** —— 真实取数器，不是假数据。

    这是当初语义修正的核心：旧版把这条路径也当成 demo，用户拿到的是
    内置快照，而真数据本来取得到。
    """
    f = build_fetcher(None, mode="public_pool")
    assert f.real is True
    assert f.auth_mode == "public_pool"
    # 惰性：构造时不实例化 Client（不联网、不耗配额）
    assert getattr(f, "_client", "unset") is None


def test_build_fetcher_credentials_mode() -> None:
    f = build_fetcher({"client_id": "x", "client_secret": "y"},
                      mode="credentials")
    assert f.real is True
    assert f.auth_mode == "credentials"
    # 关键：构造 WmshareFetcher **不会**实例化 Client（惰性）
    assert getattr(f, "_client", "unset") is None


def test_shape_as_of_is_fixed_date() -> None:
    """形状夹具的截至日必须是固定值——不能是 today（夹具要可复现）。"""
    from shape_gen import SHAPE_AS_OF

    assert SHAPE_AS_OF.count("-") == 2


# ================================================================ server

@pytest.fixture()
def live_server(tmp_path: Path):
    """起一个真实 socket 但只绑回环的服务，测试后关闭。"""
    from workbench.platform.server import _safe_join  # noqa: F401
    from workbench.tools.appinfo import handler as appinfo
    from workbench.tools.health import handler as health
    from workbench.tools.meta_tools import handler as meta_tools

    store = Store(tmp_path / "s.db")
    fetcher = FakeFetcher()
    static = tmp_path / "static"
    static.mkdir()

    class Ctx:
        registry = {"appinfo": appinfo.handle, "tools": meta_tools.handle,
                    "health": health.handle}
        auth_mode = "public_pool"
        mode_reason = ""
        credentials = creds.ResolvedCredentials("", "", source="none")
        project_url = "https://github.com/open-winmale/wmshare"

    sctx = ServerContext(store=store, fetcher=fetcher,
                         static_dir=static, registry=Ctx.registry, context=Ctx())
    httpd = serve(sctx, host=HOST, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    yield f"http://{HOST}:{port}"
    httpd.shutdown()
    httpd.server_close()
    store.close()


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310 - 本机回环
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def test_server_binds_loopback_only(live_server: str) -> None:
    """只绑 127.0.0.1——本地工具不应对局域网可达（DEBT D-07）。"""
    assert live_server.startswith("http://127.0.0.1:")


def test_server_rejects_non_loopback_host(tmp_path: Path) -> None:
    """``serve(host="0.0.0.0")`` 必须直接拒绝。"""
    sctx = ServerContext(store=Store(tmp_path / "x.db"), fetcher=FakeFetcher(),
                         static_dir=tmp_path, registry={})
    with pytest.raises(ValueError, match="127.0.0.1"):
        serve(sctx, host="0.0.0.0", port=0)


def test_server_health_has_three_states(live_server: str) -> None:
    status, body = _get(f"{live_server}/api/health")
    assert status == 200
    assert body["ok"] is True
    for key in ("hub", "db", "wmshare"):
        assert key in body["data"], f"health 缺少 {key} 态"


def test_server_appinfo_exposes_mode(live_server: str) -> None:
    status, body = _get(f"{live_server}/api/appinfo")
    assert status == 200
    assert body["data"]["auth_mode"] == "public_pool"
    assert body["data"]["real"] is True


def test_server_tools_lists_all_contract_endpoints(live_server: str) -> None:
    from workbench.core.envelope import ENDPOINTS

    status, body = _get(f"{live_server}/api/tools")
    assert status == 200
    slugs = {t["slug"] for t in body["data"]["tools"]}
    tool_slugs = {s for s, spec in ENDPOINTS.items()
                  if spec["path"].endswith("/run")}
    assert tool_slugs == slugs


def test_server_unknown_path_returns_404_with_readable_error(live_server: str) -> None:
    status, body = _get(f"{live_server}/api/nope")
    assert status == 404
    assert body["ok"] is False
    assert body["data"] == {}
    assert "未知端点" in body["meta"]["error"]
    assert body["meta"]["action"] == "fix_input"


def test_server_unimplemented_tool_returns_not_ready(live_server: str) -> None:
    """契约里有但未实现的工具 → 可读的「未接数据源」，不是 404。

    404 会让人以为路径写错了；这个区分是刻意的。
    注意 ``/api/*/run`` 都是 POST 端点，得按契约的方法发。
    """
    req = urllib.request.Request(f"{live_server}/api/dashboard/run",
                                data=b"{}", method="POST",
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310
        assert r.status == 200
        body = json.loads(r.read())
    assert body["ok"] is False
    assert body["meta"]["code"] == "not_ready"


def test_server_root_returns_hint_page_when_not_built(live_server: str) -> None:
    """未构建前端 → **HTTP 200** 提示页（本地工具不该报服务器错误）。"""
    with urllib.request.urlopen(f"{live_server}/", timeout=5) as r:  # noqa: S310
        assert r.status == 200
        assert r.headers["Cache-Control"] == "no-cache"
        html = r.read().decode("utf-8")
    assert "python -m workbench.build" in html
    assert "前端尚未构建" in html


def test_hint_page_css_is_not_fstring_escaped() -> None:
    """提示页里不得出现 ``{{``——那是 f-string 转义写法，普通字符串会原样输出。

    **真事（2026-11-26）**：``_NOT_BUILT_HTML`` 是普通字符串却把 CSS 写成
    ``body{{...}}``，于是整段样式失效：白底无样式、``<pre>`` 里的 ``#`` 被
    当标题渲染。而这是用户「装完没界面」时唯一的指引。原测试只断言「包含
    ``make web`` 字样」，所以坏了两天没人发现。
    """
    from workbench.platform.not_built import NOT_BUILT_HTML

    assert "{{" not in NOT_BUILT_HTML, "出现 f-string 转义残留 {{，CSS 会失效"
    assert "}}" not in NOT_BUILT_HTML
    # 样式必须真的生效：有选择器块，且不是被转义坏的空壳
    assert NOT_BUILT_HTML.count("{") == NOT_BUILT_HTML.count("}")


def test_hint_page_offers_nodepath_to_users() -> None:
    """提示页首选「装预构建包」（多数用户只需要这条），其次才是源码构建。

    「用户装完没界面」这个问题的正解是换用自带界面的包，而不是让终端用户
    去装 Node。指引里必须给出那条一条命令能跑完的路径。
    """
    from workbench.platform.not_built import NOT_BUILT_HTML

    assert "releases/latest/download" in NOT_BUILT_HTML
    assert "pip install" in NOT_BUILT_HTML


def test_server_serves_index_with_no_cache(live_server: str,
                                           tmp_path: Path) -> None:
    """构建后 index.html 用 ``no-cache``（可缓存但必须重验证），不是 ``no-store``。"""
    static = tmp_path / "static"
    (static / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    (static / "assets").mkdir()
    (static / "assets" / "app-abc123.js").write_text("console.log(1)",
                                                    encoding="utf-8")
    with urllib.request.urlopen(f"{live_server}/", timeout=5) as r:  # noqa: S310
        assert r.headers["Cache-Control"] == "no-cache"
        assert r.headers["Content-Type"].startswith("text/html")

    with urllib.request.urlopen(
            f"{live_server}/assets/app-abc123.js", timeout=5) as r:  # noqa: S310
        assert "immutable" in r.headers["Cache-Control"]
        assert r.headers["Content-Type"].startswith("application/javascript")


def test_server_blocks_path_traversal(live_server: str) -> None:
    """``..`` 不得逃出 static 根。"""
    status, _body = _get(f"{live_server}/assets/../../etc/passwd")
    assert status == 404


def test_server_rejects_unknown_mime(live_server: str,
                                     tmp_path: Path) -> None:
    """白名单外后缀不托管——避免把源码/配置误暴露。"""
    static = tmp_path / "static"
    (static / "index.html").write_text("<html></html>", encoding="utf-8")
    (static / "secret.py").write_text("KEY='x'", encoding="utf-8")
    status, body = _get(f"{live_server}/secret.py")
    assert status == 404
    assert body["ok"] is False


def test_server_api_prefix_takes_priority(live_server: str) -> None:
    """``/api/*`` 走 API 分支，不被静态托管吃掉。"""
    status, body = _get(f"{live_server}/api/health")
    assert status == 200
    assert body["ok"] is True


def test_server_405_when_method_mismatch(live_server: str) -> None:
    """路径对但方法不符 → 405（而非 404）。"""
    req = urllib.request.Request(f"{live_server}/api/appinfo", data=b"{}",
                                method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)  # noqa: S310
        raise AssertionError("应当返回 405")
    except urllib.error.HTTPError as exc:
        assert exc.code == 405
