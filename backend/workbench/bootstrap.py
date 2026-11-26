"""组合根：装配 store / hub / fetcher / registry，然后交给 HTTP 层。

**为什么需要单独一层**：``platform/server.py`` 不该 import ``tools``（那会让 HTTP
机制依赖业务）；但**必须有人**把 handler 注册进去。这个「有人」就是组合根——
它是唯一允许 import 全部层的地方，且**不承载业务逻辑**，只做装配。

分层校验把它单列成 ``bootstrap``（depth 4，最浅），不是为了豁免，
而是因为「装配者」在分层图里本来就是一个正当角色。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client.autoload import signature as _unused  # noqa: F401  (保持层依赖可见)
from .client.fetchers import (
    MODE_MISSING,
    build_fetcher,
    resolve_auth_mode,
    wmshare_installed,
)
from .client.hub import DataHub
from .platform import credentials as creds
from .platform.server import DEFAULT_PORT, HOST, ServerContext, serve
from .platform.store import Store

__all__ = ["Context", "build_context", "run_server"]

#: 页顶/终端显示的访问方式文案（三档，与 ``client.fetchers`` 一一对应）。
_MODE_LABELS: dict[str, str] = {
    "credentials": "自有凭证模式",
    "public_pool": "免注册模式（真实数据）",
    "missing": "未接入数据源",
}


@dataclass
class Context:
    """注入给 handler 的上下文（与 ``platform.server.ServerContext`` 同形）。

    handler 只依赖本对象的属性，不 import 具体实现，便于测试替换。

    ``auth_mode`` 是三种访问方式之一（见 ``client/fetchers`` 模块 docstring）：
    ``credentials`` / ``public_pool`` / ``missing``。前两者都是真实数据；
    ``missing`` 时任何取数都会以可分类异常失败（``MissingFetcher``）。
    """

    store: Any
    hub: Any
    fetcher: Any
    auth_mode: str
    credentials: Any
    registry: dict[str, Any]
    #: ``missing`` 态的**原因**（未装 SDK / 免注册被禁用且无凭证）。
    #: 其余方式为空串。UI 据此告诉用户「怎样才能接入真实数据」。
    mode_reason: str = ""


def _static_dir() -> Path:
    """前端产物目录（``backend/workbench/static``）。"""
    return Path(__file__).resolve().parent / "static"


def _load_registry() -> dict[str, Any]:
    """注册已实现的 handler。新增工具在此加一行。

    ``slug`` 必须与 ``core.envelope.ENDPOINTS`` 一致，否则服务层拿不到路由。
    """
    from .tools.appinfo import handler as appinfo
    from .tools.assistant import handler as assistant
    from .tools.backtest import handler as backtest
    from .tools.dashboard import handler as dashboard
    from .tools.ec_estimate import handler as ec_estimate
    from .tools.economics import handler as economics
    from .tools.equity import handler as equity
    from .tools.health import handler as health
    from .tools.key import handler as key
    from .tools.markets import handler as markets
    from .tools.meta_tools import handler as meta_tools
    from .tools.portfolio import handler as portfolio
    from .tools.screener import handler as screener
    from .tools.sources import handler as sources
    from .tools.watchlist import handler as watchlist

    return {
        "appinfo": appinfo.handle,
        "tools": meta_tools.handle,
        "health": health.handle,
        "sources": sources.handle,
        "watchlist": watchlist.handle,
        "markets": markets.handle,
        "economics": economics.handle,
        "backtest": backtest.handle,
        "dashboard": dashboard.handle,
        "screener": screener.handle,
        "equity": equity.handle,
        "portfolio": portfolio.handle,
        "ec_estimate": ec_estimate.handle,
        "key": key.handle,
        "assistant": assistant.handle_info,
        "assistant_chat": assistant.handle_chat,
        "assistant_stream": assistant.handle_stream,
        "assistant_stop": assistant.handle_stop,
        "assistant_sessions": assistant.handle_sessions,
        "assistant_session": assistant.handle_session,
    }


def build_context(*, store: Any = None, fetcher: Any = None,
                  cred_path: Path | None = None,
                  env: dict[str, str] | None = None) -> Context:
    """装配运行期上下文。

    访问方式由 ``client.fetchers.resolve_auth_mode`` 判定（三档，见该模块）。
    关键点：**没配凭证不等于没数据** —— 装了 wmshare 就走免注册真实取数；
    只有「未装 SDK」或「免注册被禁且无凭证」才是 ``missing`` 态。

    :param fetcher: 测试注入点。传入时跳过模式判定与构造，直接使用
        （``auth_mode`` 取注入对象的），离线测试由此做到零网络零配额。
    """
    st = store if store is not None else Store()
    resolved = creds.resolve(st, env=env, cred_path=cred_path)

    if fetcher is not None:
        auth_mode = str(getattr(fetcher, "auth_mode", "credentials"))
        mode_reason = ""
    else:
        auth_mode = resolve_auth_mode(has_credentials=resolved.present)
        fetcher = build_fetcher(
            {"client_id": resolved.client_id,
             "client_secret": resolved.client_secret,
             "market": resolved.market},
            mode=auth_mode)
        mode_reason = _missing_reason() if auth_mode == MODE_MISSING else ""

    return Context(
        store=st,
        hub=DataHub(),
        fetcher=fetcher,
        auth_mode=auth_mode,
        credentials=resolved,
        registry=_load_registry(),
        mode_reason=mode_reason,
    )


def _missing_reason() -> str:
    """未接入态的原因——UI 要据此告诉用户「怎样才能接入真实数据」。

    只写「未接入」不写原因，用户无从知道是自己没装 SDK、还是免注册被禁了。
    判定**经 ``client.fetchers`` 模块转发**而不是直接用顶部导入的函数——
    否则测试 monkeypatch 不了它（模块绑定会绕过补丁）。
    """
    from .client import fetchers

    if not fetchers.wmshare_installed():
        return "未安装 wmshare（pip install \".[data]\"）"
    return "已设置 WMSHARE_DISABLE_ANON=1，且未配置凭证"


def run_server(*, port: int = DEFAULT_PORT, store: Any = None,
               host: str = HOST) -> None:
    """装配并阻塞运行（CLI 入口用）。"""
    ctx = build_context(store=store)
    server_ctx = ServerContext(
        store=ctx.store, fetcher=ctx.fetcher,
        static_dir=_static_dir(), registry=ctx.registry)
    # 把 Context 挂到 ServerContext，供 handler 读取 credentials / hub
    server_ctx.context = ctx  # type: ignore[attr-defined]

    httpd = serve(server_ctx, host=host, port=port)
    mode = _MODE_LABELS.get(ctx.auth_mode, ctx.auth_mode)
    print(f"\n  wmshare-workbench · {mode}")
    print(f"  → http://{host}:{httpd.server_address[1]}/\n")
    if ctx.auth_mode == MODE_MISSING:
        print(f"  未接入：{ctx.mode_reason}")
        print("  装好 wmshare 后重启即用免注册真实数据：`pip install \".[data]\"`\n")
    elif ctx.auth_mode == "public_pool":
        print("  数据为真实数据（免注册访问，服务端按来源网络记账）。")
        print("  配自有凭证可获得独立额度：`wmshare setup`\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
    finally:
        httpd.server_close()
        try:
            ctx.store.close()
        except Exception:  # noqa: BLE001 - 关闭失败不影响退出
            pass
