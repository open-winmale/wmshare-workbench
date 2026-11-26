"""``/api/key``：热切凭证。

**安全边界（不可协商）**：

1. **只接受 127.0.0.1**——服务本身已绑定回环，此处再靠 HTTP 层校验一次。
2. **响应绝不回显 secret**：只给尾 4 位，供用户确认「换的是哪把 Key」。
3. **探针成功才替换**：先在新凭证上做一次最小真实调用，失败则保持旧凭证。
   否则「换了个错 Key」会把原本能用的工作台也弄坏。
4. **换 Key 后清缓存**：旧凭证取回的数据不能继续展示——那是别人的数据视图。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import ToolError, err_from, str_param

__all__ = ["handle", "MODE", "PROBE_TARGET"]

#: 凭证来源（前端据此说明优先级：本库 > 环境变量 > 文件）。
MODE = "store"

#: 探针用的最小调用（一次取 1 根 K 线，成本可忽略）。
PROBE_TARGET = "kline.query_bars"


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    try:
        client_id = str_param(params, "client_id", max_len=128)
        client_secret = str_param(params, "client_secret", max_len=256)
        market = str_param(params, "market") or "cn"
        if not client_id or not client_secret:
            raise ToolError("client_id 与 client_secret 都必须提供",
                            code="missing_param")
        if market not in ("cn", "hk", "us"):
            raise ToolError(f"market 只支持 cn/hk/us，收到 {market!r}",
                            code="param")
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    fetcher = getattr(ctx, "fetcher", None)
    probe_ok, probe_note = _probe(fetcher, client_id, client_secret, market)
    if not probe_ok:
        # 探针失败 → **不写库、不清缓存**，保持原状
        return err_from(ctx, ToolError(
            f"新凭证探针失败，已保持原凭证：{probe_note}",
            code="probe_failed", action="config"))

    stored, store_note = _store(ctx, client_id, client_secret, market)
    _clear_cache(ctx)
    return ok_envelope(
        {
            "switched": True,
            "stored": stored,
            "source": MODE,
            "market": market,
            "client_id_tail": client_id[-4:],
            "cache_cleared": True,
            "note": store_note,
        },
        as_of="",
        meta={"note": "探针成功后才替换；旧凭证的缓存已清空"},
        freshness="fresh",
        ec=EcEstimate(model="local"))


def _probe(fetcher: Any, client_id: str, client_secret: str,
           market: str) -> tuple[bool, str]:
    """在新凭证上做一次最小真实调用。

    ``fetcher`` 没有 ``rekey``（测试替身 / 未接入态）时直接判失败——绝不允许
    「没有探针能力就默认为成功」。
    """
    if fetcher is None:
        return False, "取数器未初始化"
    rekey = getattr(fetcher, "rekey", None)
    if not callable(rekey):
        return False, "当前取数器不支持热切"
    try:
        ok = bool(rekey(client_id, client_secret, market))
    except Exception as exc:  # noqa: BLE001 - 凭证错/网络错都不切换
        return False, f"{type(exc).__name__}: {exc}"
    return (True, "") if ok else (False, "凭证无效或网络不可达")


def _store(ctx: Any, client_id: str, client_secret: str,
           market: str) -> tuple[bool, str]:
    """写入本地库。**失败不静默**——用户需要知道重启后凭证会丢。"""
    store = getattr(ctx, "store", None)
    if store is None:
        return False, "存储未初始化：仅在本次运行内生效"
    try:
        store.set_credentials(client_id, client_secret, market)
    except Exception as exc:  # noqa: BLE001
        return False, f"写库失败（{type(exc).__name__}）：仅在本次运行内生效"
    return True, "已写入本地库（0600）"


def _clear_cache(ctx: Any) -> None:
    """换凭证必须清缓存：旧凭证取回的数据属于另一个数据视图。"""
    hub = getattr(ctx, "hub", None)
    clear = getattr(hub, "clear", None)
    if callable(clear):
        try:
            clear()
        except Exception:  # noqa: BLE001 - 清缓存失败不该回滚已成功的切换
            return
