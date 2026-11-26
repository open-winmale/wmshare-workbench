"""取数适配器：把 wmshare 的调用收敛到一个协议，便于测试替换与未接入态。

**访问方式**（这是本层最重要的语义，曾搞错过一次）：

| ``auth_mode`` | 条件 | 数据 | 页顶应显示 |
|---|---|---|---|
| ``credentials`` | 配了自有凭证 | **真实** | 自有凭证 |
| ``public_pool`` | 装了 wmshare、**没配凭证** | **真实**（免注册） | 免注册 |
| ``missing`` | 未装 wmshare，或免注册被禁且无凭证 | 无（请求以可分类异常失败） | 未接入 · 原因 |

**曾经的设计错在把 ``public_pool`` 并进了 ``demo``**：那时「装了 wmshare 但没配
凭证」会落到内置假数据——而 ``Client.from_env()`` 在凭证双缺时**本就能免注册
真实取数**（``auth_mode == "public_pool"``，由服务端按来源网络记账）。
结果是：用户装了 SDK、直接启动，看到的是一屏假数字，而真数据本来取得到。

**demo 模式已整体移除**（2026-11-27）：内置假快照让「假数字和真数字长得
一模一样」，这与「不骗人」原则相悖；免注册已是无需凭证的真实数据，演示态
没有存在价值。原内置快照整体迁往 ``tests/shape_*.py`` 作为离线形状夹具。
「未接入」态改为 :class:`MissingFetcher`——任何取数都以可分类异常失败，
由 ``err_from`` 统一映射为 ``action=config``（前端给配置指引），
**绝不返回长得像真数据的空壳**。

**为什么测试里禁止构造真实 ``Client``**：不是因为它「不合法」，而是因为
测试必须离线且零配额。免注册也是真实请求、真实记账，所以测试一律用
``FakeFetcher``。

**为什么不用 ``wmshare.Client`` 的类型**：wmshare 是可选运行时依赖。协议层只声明
行为（``call`` + ``cost_estimate``），不 import 其类型，这样未装 wmshare 也能启动。
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "AuthMode",
    "Fetcher",
    "FakeFetcher",
    "MissingFetcher",
    "NotReadyError",
    "WmshareFetcher",
    "build_fetcher",
    "catalog_records",
    "resolve_auth_mode",
    "wmshare_installed",
]

#: 访问方式字面量（与页顶显示一一对应）。
AuthMode = str
MODE_CREDENTIALS: AuthMode = "credentials"
MODE_PUBLIC_POOL: AuthMode = "public_pool"
MODE_MISSING: AuthMode = "missing"


def wmshare_installed() -> bool:
    """是否装了 wmshare。未装时无从取真实数据。"""
    try:
        import wmshare  # noqa: F401
    except ImportError:
        return False
    return True


def _anon_disabled() -> bool:
    """``WMSHARE_DISABLE_ANON=1`` 时 SDK 不回落免注册。

    此时「没凭证」真的取不到数据，必须如实报错——不能假装有数据。
    """
    return str(os.environ.get("WMSHARE_DISABLE_ANON") or "").strip() == "1"


def resolve_auth_mode(*, has_credentials: bool) -> AuthMode:
    """决定访问方式。

    顺序有意义：

    1. 有凭证 → ``credentials``。
    2. 装了 wmshare 且未禁用免注册 → ``public_pool``（**真实数据**）。
    3. 其余 → ``missing``（诚实未接入：UI 说明原因与补救办法）。
    """
    if has_credentials:
        return MODE_CREDENTIALS
    if wmshare_installed() and not _anon_disabled():
        return MODE_PUBLIC_POOL
    return MODE_MISSING


class NotReadyError(Exception):
    """「未接入数据源」时发起的取数请求。

    单独成类而不是复用 ``RuntimeError``：``err_from`` 要把它映射为
    ``action=config``（前端给配置指引），而不是 ``report``。
    """


@runtime_checkable
class Fetcher(Protocol):
    """取数协议。所有工具只依赖这两个方法。"""

    #: 是否是真实数据（``credentials`` 与 ``public_pool`` 都算真实）
    real: bool

    #: 访问方式：``credentials`` / ``public_pool`` / ``missing``
    auth_mode: AuthMode

    def call(self, target: str, **params: Any) -> Any:
        """调用一个**目录函数**（``kline.query_bars`` 这类）。"""
        ...

    def facade(self, namespace: str, method: str, **params: Any) -> Any:
        """调用**组合门面**（``cli.screener.query`` 这类）。

        目录函数与组合门面是两条不同的调用路径：前者在目录里有名字、
        ``call()`` 直达；后者由 SDK 客户端组合多次底层调用，``call()``
        会抛 ``CatalogError``。协议层必须同时声明两者。
        """
        ...

    def cost_estimate(self, target: str, **params: Any) -> dict[str, Any]:
        """离线预估 EC；无模型时 ``ec_lo``/``ec_hi`` 应为 ``None``。"""
        ...


class WmshareFetcher:
    """真实取数：惰性构造 ``wmshare.Client``。

    惰性很重要——构造时才会做凭证校验与目录加载；只需要 ``/api/health``
    的场景不应该付这个代价（实测构造零网络，但保持惰性仍是好习惯）。

    ``auth_mode`` 由**实际拿到的 client** 决定（``credentials`` 或
    ``public_pool``），不是由「有没有传凭证」猜——SDK 才是真源。
    """

    real = True

    def __init__(self, credentials: dict[str, str] | None = None,
                 client: Any = None) -> None:
        self._credentials = credentials or {}
        self._client = client
        self._auth_mode: str = MODE_CREDENTIALS if client is not None \
            else self._guess_mode()

    def _guess_mode(self) -> str:
        """构造前先按凭证推断；拿到 client 后以 ``client.auth_mode`` 为准。"""
        has = bool(self._credentials.get("client_id")
                   and self._credentials.get("client_secret"))
        return MODE_CREDENTIALS if has else MODE_PUBLIC_POOL

    @property
    def auth_mode(self) -> str:
        return self._auth_mode

    @property
    def client(self) -> Any:
        """惰性构造；失败时抛出原始异常（由调用方分类）。"""
        if self._client is None:
            import wmshare  # 延迟导入：可选依赖

            cid = self._credentials.get("client_id") or None
            sec = self._credentials.get("client_secret") or None
            market = self._credentials.get("market") or "cn"
            if cid and sec:
                self._client = wmshare.Client(client_id=cid,
                                              client_secret=sec, market=market)
            else:
                # 免注册访问：不申领、不落盘，服务端按来源网络记账。
                # 这是**真实数据**——见模块 docstring 的访问方式表。
                self._client = wmshare.Client.from_env(market=market)
            # SDK 是真源：用它实际采用的访问方式覆盖推断值
            self._auth_mode = str(getattr(self._client, "auth_mode",
                                          self._auth_mode))
        return self._client

    def call(self, target: str, **params: Any) -> Any:
        """调用一个**目录函数**（``kline.query_bars`` 这类）。

        **组合门面不能用这个方法** —— ``screener.query`` / ``backtest.run``
        不在目录里（它们由 SDK 在客户端组合多次调用），``client.call()``
        会抛 ``CatalogError: 未知函数``。那类入口请用 :meth:`facade`。
        """
        return self.client.call(target, **params)

    def facade(self, namespace: str, method: str, **params: Any) -> Any:
        """调用**组合门面**（``cli.screener.query`` / ``cli.backtest.run``）。

        ``namespace`` 是 SDK 友好命名空间（``screener`` / ``backtest`` /
        ``dividend`` …），内部由 SDK 组合多次底层调用。
        """
        ns = getattr(self.client, namespace)
        return getattr(ns, method)(**params)

    def cost_estimate(self, target: str, **params: Any) -> dict[str, Any]:
        try:
            return self.client.cost_estimate(target, **params)
        except Exception:  # noqa: BLE001 - 估算失败不该阻断
            return {"ec_lo": None, "ec_hi": None, "model": "unavailable"}

    def catalog_search(self, query: str, limit: int = 10) -> list[dict]:
        """数据目录关键词检索（AI 助手「先查目录再取数」纪律的入口）。

        ``cat`` 是客户端目录（不联网、零 EC）。经模块级 ``wmshare.load()``
        而不是 ``self.client`` 上的命名空间访问——``load`` 不在目录命名
        空间里，走 client 属性会撞 CatalogError。
        """
        import wmshare

        rows = wmshare.load().search(query)
        return catalog_records(rows)[:limit]

    def rekey(self, client_id: str, client_secret: str,
              market: str = "cn") -> bool:
        """热切凭证：先在**新** client 上做真实探针，成功才替换。

        探针失败则保持旧 client——避免「换了个错 Key 导致原来能用的也不能用了」。
        """
        try:
            import wmshare

            probe = wmshare.Client(client_id=client_id, client_secret=client_secret,
                                   market=market)
            probe.call("kline.query_bars", sym="600519", limit=1)
        except Exception:  # noqa: BLE001 - 凭证错/网络错都不切换
            return False
        self._client = probe
        self._credentials = {"client_id": client_id,
                             "client_secret": client_secret, "market": market}
        return True


class MissingFetcher:
    """未接入态取数器：任何取数请求都以**可分类的异常**失败。

    为什么不是「返回空数据」：空数据和「没有配置」长得很像，会把配置
    问题伪装成数据问题——用户会以为「这股票没数据」而不是「我没接入」。
    抛 :class:`NotReadyError`，让 ``err_from`` 统一映射为 ``action=config``。
    """

    real = False
    auth_mode = MODE_MISSING

    def __init__(self, reason: str = "") -> None:
        #: 未接入的原因（UI 据此告诉用户怎样才能接入真实数据）。
        self.reason = reason

    def _fail(self, target: str) -> None:
        raise NotReadyError(
            f"未接入数据源（{self.reason or '未安装 wmshare 或未配置凭证'}），"
            f"取数请求 {target} 未执行")

    def call(self, target: str, **params: Any) -> Any:
        self._fail(target)

    def facade(self, namespace: str, method: str, **params: Any) -> Any:
        self._fail(f"{namespace}.{method}")

    def cost_estimate(self, target: str, **params: Any) -> dict[str, Any]:
        # 未接入态没有成本模型：``pred_*`` 为 None（不是 0——0 会被读成免费），
        # ``model`` 说明原因，让「无模型」与「模型说很便宜」可区分。
        return {"ec_lo": None, "ec_hi": None, "model": "unavailable"}


class FakeFetcher:
    """测试替身：返回注入的固定数据，**绝不联网**。

    数据表在 ``tests/shape_*.py``（原内置快照迁入测试侧）。两种用法：

    - ``FakeFetcher(resolver=shape_for)``：挂形状夹具，行为对齐旧内置快照；
    - ``FakeFetcher(data={target: value})``：只注入个别 target。

    未注入且无 resolver 的 target 直接 ``KeyError``——**宁可红也不能
    静默给假数据**，那是 demo 模式留下的教训。
    """

    real = False
    auth_mode = "fake"

    def __init__(self, data: dict[str, Any] | None = None,
                 resolver: Any = None) -> None:
        #: 覆盖表（测试注入特定返回用）。
        self._override = dict(data or {})
        #: 兜底解析器（``shape_for(target, params)``），测试挂形状夹具用。
        self._resolver = resolver
        #: 记录被调用过的 target（测试断言「零请求」/「只发一次」用）
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _resolve(self, target: str, params: dict[str, Any]) -> Any:
        if target in self._override:
            return self._override[target]
        if self._resolver is not None:
            return self._resolver(target, params)
        raise KeyError(f"FakeFetcher 未注入 {target}"
                       "（测试应显式注入 data 或挂 resolver）")

    def call(self, target: str, **params: Any) -> Any:
        self.calls.append((target, params))
        return self._resolve(target, params)

    def facade(self, namespace: str, method: str, **params: Any) -> Any:
        """组合门面记成一次调用（``ns.method`` 作为 target）。

        形状夹具以 ``screener.query`` 这样的点号键存放，与真实门面名一致。
        """
        target = f"{namespace}.{method}"
        self.calls.append((target, params))
        return self._resolve(target, params)

    def cost_estimate(self, target: str, **params: Any) -> dict[str, Any]:
        # 测试替身没有成本模型：``pred_*`` 为 None（不是 0——0 会被读成免费），
        # ``model`` 说明原因，让「无模型」与「模型说很便宜」可区分。
        return {"ec_lo": None, "ec_hi": None, "model": "unavailable"}


def catalog_records(raw: Any) -> list[dict[str, Any]]:
    """目录检索结果 → ``list[dict]``（鸭子类型，不 import pandas）。"""
    to_records = getattr(raw, "to_dict", None)
    if callable(to_records):
        try:
            records = to_records("records")
        except (TypeError, ValueError):
            records = None
        if isinstance(records, list):
            return [r for r in records if isinstance(r, dict)]
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def build_fetcher(credentials: dict[str, str] | None, *,
                  mode: AuthMode) -> Fetcher:
    """按**已判定的访问方式**选实现。

    语义由 :func:`resolve_auth_mode` 决定，这里只做映射——把判定逻辑
    再写一遍会让「哪种情况取不到数据」这件事出现在两个地方。

    :param mode: ``credentials`` / ``public_pool`` / ``missing``
    """
    if mode == MODE_MISSING:
        return MissingFetcher()
    return WmshareFetcher(credentials)
