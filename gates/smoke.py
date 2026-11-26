#!/usr/bin/env python3
"""真实模式全工具冒烟（**手动命令，不在 make check 里**）。

**为什么存在**：D-27 已四连——演示数据捏的形状与真实返回不同，页面在
演示态全绿、配上凭证才崩（选股恒空、自选四列、估值停季末、宏观序列）。
离线契约测试钉的是「走哪条路径」，钉不住「真实返回的形状」。本脚本对
**运行中的服务**逐工具发真实请求，断言关键块非空——把「演示绿真实崩」
从用户在页面上撞见，变成一轮冒烟扫出来。

用法：先启动服务，再 ``make smoke``（真实模式，自有凭证）或
``python3 gates/smoke.py --port 8798``（对另一个端口上的实例跑同一套断言）。
**CI 不跑**（无凭证、无服务）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request

__all__ = ["main"]

#: 冒烟用的样例标的与回测区间（区间必填：不给会按 need_range 拒绝）。
SYMBOL = "600519"
BEGIN = (dt.date.today() - dt.timedelta(days=400)).isoformat()
END = dt.date.today().isoformat()

TRADES = [
    {"code": "600519", "side": "buy", "price": 1300.0, "shares": 100, "date": "2025-03-05"},
    {"code": "600519", "side": "sell", "price": 1450.0, "shares": 40, "date": "2025-09-10"},
    {"code": "000001", "side": "buy", "price": 10.5, "shares": 2000, "date": "2025-06-20"},
]


def check(name: str, slug: str, body: dict[str, object], *asserts: tuple[str, object], unwrap=None):
    """登记一条冒烟：``asserts`` 是 (标签, 断言函数(data)->bool) 对。

    ``unwrap``：信封 ``data`` 到断言视图的变换。equity 是唯一**双层
    嵌套**（``data.data`` 才是分区载荷，FE 读的正是这个）——写这条冒烟
    时连作者都被绊了一下，所以把它显式化而不是让每个断言各剥一层。
    """
    return (name, slug, body, list(asserts), unwrap)


#: 全工具冒烟清单。断言只看 ``data``——信封 ``ok`` 与警告由统一逻辑先查。
CHECKS = [
    check(
        "dashboard",
        "dashboard",
        {},
        ("indices>=3", lambda d: len(d.get("indices") or []) >= 3),
        ("indices有pe", lambda d: all(r.get("pe") is not None for r in d.get("indices") or [])),
        ("trading_day", lambda d: bool(d.get("trading_day"))),
        ("breadth", lambda d: bool(d.get("breadth"))),
        ("moneyflow", lambda d: bool(d.get("moneyflow"))),
        # 今日盘面三卡：date 守卫后可能少 cyb（上游间歇断供），>=2 且真行必备价
        ("盘面卡>=2", lambda d: len(d.get("index_cards") or []) >= 2),
        ("盘面卡有价", lambda d: all(c.get("close") is not None for c in d.get("index_cards") or [])),
        ("分布桶", lambda d: len((d.get("distribution") or {}).get("bins") or []) >= 1),
        ("涨幅榜", lambda d: len((d.get("distribution") or {}).get("gainers") or []) >= 1),
        ("跌幅榜", lambda d: len((d.get("distribution") or {}).get("losers") or []) >= 1),
    ),
    check(
        "watchlist",
        "watchlist",
        {},
        ("rows>=3", lambda d: len(d.get("rows") or []) >= 3),
        ("有名称", lambda d: any((r.get("name") or "—") != "—" for r in d.get("rows") or [])),
        ("有5日涨跌", lambda d: any(r.get("chg_5d") is not None for r in d.get("rows") or [])),
        ("有量比", lambda d: any(r.get("vol_ratio_5") is not None for r in d.get("rows") or [])),
        ("有行级日期", lambda d: any(r.get("kline_date") for r in d.get("rows") or [])),
        ("request_count==2", lambda d: d.get("request_count") == 2),
    ),
    check(
        "markets",
        "markets",
        {},
        ("breadth", lambda d: bool(d.get("breadth"))),
        ("movers>=1", lambda d: len(d.get("movers") or []) >= 1),
        ("trading_day", lambda d: bool(d.get("trading_day"))),
    ),
    check(
        "equity概览",
        "equity",
        {"symbol": SYMBOL},
        ("有名称", lambda d: bool((d.get("snapshot") or {}).get("name"))),
        ("有现价", lambda d: (d.get("snapshot") or {}).get("close") is not None),
        unwrap=lambda d: d.get("data") or {},
    ),
    check(
        "equity季报",
        "equity",
        {"symbol": SYMBOL, "section": "statements", "domain": "indicators", "period": "quarter"},
        (
            "期次是YYYY-Qn",
            lambda d: bool(d.get("periods")) and str(d["periods"][0]).startswith("2026-Q"),
        ),
        ("有科目", lambda d: bool(d.get("rows"))),
        unwrap=lambda d: d.get("data") or {},
    ),
    check(
        "equity行情走势",
        "equity",
        {"symbol": SYMBOL, "section": "bars", "days": 60},
        ("bars>=20", lambda d: len(d.get("bars") or []) >= 20),
        ("有末日", lambda d: bool(d.get("last_date"))),
        unwrap=lambda d: d.get("data") or {},
    ),
    check(
        "equity分时",
        "equity",
        {"symbol": SYMBOL, "section": "minute"},
        ("有点数", lambda d: len(d.get("bars") or []) >= 1),
        ("intraday", lambda d: d.get("intraday") is True),
        ("有更新时间", lambda d: bool(d.get("updated_at"))),
        unwrap=lambda d: d.get("data") or {},
    ),
    check(
        "screener",
        "screener",
        {"where": "$PE_TTM < 15", "limit": 5},
        ("total>0", lambda d: (d.get("total") or 0) > 0),
        ("rows>=1", lambda d: len(d.get("rows") or []) >= 1),
    ),
    check(
        "economics",
        "economics",
        {"code": "$CPI"},
        ("series>=1", lambda d: len(d.get("series") or []) >= 1),
        ("curve==6", lambda d: len(d.get("curve") or []) == 6),
        ("fx>=1", lambda d: len(d.get("fx") or []) >= 1),
        ("无结构异常", lambda d: "异常" not in str(d.get("series_note"))),
    ),
    check(
        "backtest",
        "backtest",
        {"symbol": SYMBOL, "begin": BEGIN, "end": END},
        ("equity>=1", lambda d: len(d.get("equity") or []) >= 1),
        ("有价格K线", lambda d: len(d.get("bars") or []) >= 1),
    ),
    check(
        "portfolio",
        "portfolio",
        {"trades": TRADES},
        ("rows>=1", lambda d: len(d.get("rows") or []) >= 1),
        ("有名称", lambda d: any((r.get("name") or "—") != "—" for r in d.get("rows") or [])),
        (
            "全部有价",
            lambda d: (d.get("totals") or {}).get("valued") == (d.get("totals") or {}).get("total"),
        ),
    ),
    check(
        "sources",
        "sources",
        {},
        ("rows>=1", lambda d: (d.get("count") or 0) >= 1),
    ),
]


def run_one(base: str, slug: str, body: dict[str, object]) -> dict[str, object]:
    """POST /api/{slug}/run；HTTP/JSON 错误原样抛（上层统一标 FAIL）。"""
    req = urllib.request.Request(
        f"{base}/api/{slug}/run",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="真实模式全工具冒烟")
    parser.add_argument("--port", type=int, default=8799)
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}"

    failed: list[str] = []
    for name, slug, body, asserts, unwrap in CHECKS:
        try:
            env = run_one(base, slug, body)
        except Exception as exc:  # noqa: BLE001 - 连接/超时/HTTP 错误都算 FAIL
            print(f"FAIL {name}: 请求失败 {exc}")
            failed.append(name)
            continue
        if not env.get("ok"):
            meta = env.get("meta") or {}
            print(f"FAIL {name}: ok=false code={meta.get('code')} {str(meta.get('note'))[:80]}")
            failed.append(name)
            continue
        data = env.get("data") or {}
        if unwrap is not None:
            data = unwrap(data)
        bad = [label for label, fn in asserts if not fn(data)]
        if bad:
            print(f"FAIL {name}: {', '.join(bad)}")
            failed.append(name)
            continue
        warn = "；".join(env.get("warnings") or [])
        print(f"PASS {name}" + (f"（告警：{warn[:60]}）" if warn else ""))

    print(
        f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} 通过"
        + (f"；失败：{'、'.join(failed)}" if failed else "")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
