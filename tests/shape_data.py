"""形状夹具（测试专用） —— 装配与分发（``target`` + 参数 → 返回值）。

**形状必须与真实返回逐字段一致**。这条纪律不是洁癖：演示态与实时态如果
返回不同结构，前端会在演示态下跑通、在实时态下崩——而且是在用户配好
凭证之后才崩，那时他已经在看「生产数据」了，错误的可信度最高。

因此字段名、单位、嵌套层级都取自 ``../wmshare/docs/api_pack_samples.json``
（维护者联网拍摄的真实响应）与 ``docs/API.md`` 的 ``returns_shape`` 声明。

模块分工（每个文件只做一件事）：

- ``shape_gen``    通用生成器（行情/宏观/估值/分红/三表…）
- ``shape_extra``  业绩披露与收益拆解（结构最复杂的两族）
- ``shape_bind`` 按参数收窄的规则（未知码不造假、未收录不补数…）
- ``shape_data``   本文件：装配 SHAPE_DATA + 分发

**演示日固定为 ``SHAPE_AS_OF``**，不用 ``date.today()``：形状夹具（测试专用）必须能
一眼看出「这是快照，不是今天的」。
"""

from __future__ import annotations

from typing import Any

import shape_bind
from shape_extra import shape_decomp, shape_forecast, shape_forecast_latest
from shape_gen import (
    SHAPE_AS_OF,
    SHAPE_SYMBOLS,
    _fundamental_payload,
    _macro_payload,
    _market_payload,
)
from shape_bind import shape_statement_rows

__all__ = ["SHAPE_AS_OF", "SHAPE_DATA", "SHAPE_SYMBOLS", "shape_for"]

SHAPE_DATA: dict[str, Any] = {
    **_market_payload(),
    **_macro_payload(),
    **_fundamental_payload(),
}

# 收窄规则要知道形状夹具（测试专用）本身（按 sym 取那一份），在这里绑定一次。
shape_bind.bind(SHAPE_DATA)

#: 需要按参数收窄的 target → 处理器。未登记的直接返回 ``SHAPE_DATA``。
#:
#: 收窄逻辑**属于各模块自己的职责**（``shape_bind`` / ``shape_extra``），
#: 这里只做登记：把实现写在这张表旁边会让本模块随数据族增加一路长下去。
_RESHAPERS: dict[str, Any] = {
    "indices.valuation": shape_bind.shape_index_valuation,
    "index.trend": shape_bind.shape_index_trend,
    "kline.query_min1_live": shape_bind.shape_min1_live,
    "kline.query_index_min1_live": shape_bind.shape_index_min1_live,
    "kline.query_last_live": shape_bind.shape_last_live,
    "kline.query_last_live_many": shape_bind.shape_live_many,
    "screener.index_top_movers": shape_bind.shape_top_movers,
    "macro.query": shape_bind.shape_macro_query,
    "macro.bond_curve": shape_bind.shape_bond_curve,
    "forecast.snapshot": shape_forecast,
    "forecast.yjyg_latest": shape_forecast_latest,
    "income.decomp_one": shape_decomp,
    # 报表四表按 period 变形（annual=年份键 / quarter=季报累计档）
    **{f"statements.{m}": (lambda t: lambda p: shape_statement_rows(t, p))(
           f"statements.{m}")
       for m in ("indicators", "income", "balance", "cashflow")},
}


def shape_for(target: str, params: dict[str, Any] | None = None) -> Any:
    """按 target 取形状夹具（测试专用）。

    带参数的 target（如 ``kline.snapshot`` 传了 ``sym``）在这里按参数
    收窄——否则前端切标的时会看到「数据不跟着变」，那是形状夹具（测试专用）最容易
    露馅的地方。
    """
    params = params or {}
    if target in shape_bind.PER_SYMBOL_TARGETS:
        return shape_bind.shape_per_symbol(target, params)
    shaper = _RESHAPERS.get(target)
    if shaper is not None:
        return shaper(params)
    return SHAPE_DATA.get(target)
