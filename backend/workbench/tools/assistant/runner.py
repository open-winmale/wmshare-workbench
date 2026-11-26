"""单 agent 装配：一个模型、一套按域分组的工具面、一个执行闭包。

**为什么从多 agent 收回**（2026-11-27 实测）：每次 delegate 至少多两跳
模型请求，端到端延迟成倍；数据面只有十几件工具时，单 agent 一次取数
（可并行调用多个工具）比「编排→专员→回编排」快得多。

**注意力仍然靠分类而不是分角色**：

- 工具清单按域分组（``【行情】【基本面】…`` 前缀 + 固定域序）；
- 系统提示只放每域一行卡片，细口径用 ``read_skill`` 按需读；
- 昂贵工具在描述里标明，执行器仍守单轮 EC 预算。

扩展方式不变：新能力 = ``registry.json`` 加条目；新域 = 加 SKILL.md。
"""

from __future__ import annotations

from typing import Any

from . import executor
from .config import LLMConfig
from .ledger import SourceLedger
from .skills import Skill, domain_cards

__all__ = ["build_system_prompt", "build_tools", "make_execute_fn"]

#: 工具清单的域序（系统提示、工具数组都按它排——同一分类口径）。
DOMAIN_ORDER = ("market", "fundamental", "screen", "macro", "portfolio", "meta")

#: 单 agent 系统提示——**字节稳定**（不含日期等任何动态内容，动态全进消息尾）。
_PROMPT_TMPL = """你是 wmshare-workbench 的投研数据助手，跑在用户本机。

铁律（违反任何一条都是失败的回答）：
1. 数字必须来自工具结果；引用来源写 [n]（n 是工具结果前「来源 n：」的编号）。
2. 每个关键数字都要带口径：数据日期 / 报告期 / 单位。缺是缺、旧是旧，不编造。
3. 先判断问题属于哪些域，直接取数；一次可以同时调用多个工具，不要逐轮试探。
4. 昂贵数据（财报/选股）只在用户明确需要时取，范围收敛。
5. 不做投资建议、不给目标价、不预测涨跌；用户要决策时给数据两面并加
   「本回答不构成投资建议」。
6. 回答用简体中文；表格优先；结尾如有 [n] 引用则自然收束，不加空话。

数据分域（工具描述前的【】就是域；口径/字段拿不准时先 read_skill(域 id)）：
{domain_cards}

指标码/接口是否存在拿不准时先 catalog_search，不要猜码。
"""

_READ_SKILL: dict[str, Any] = {
    "name": "read_skill",
    "description": "读一个领域的数据口径纪律（单位/分位/缺失语义/该用哪个工具）。"
                   "拿不准口径、或要解释某个数字时先读它；日常取数不必读。",
    "parameters": {"type": "object", "properties": {
        "id": {"type": "string",
               "description": "领域 id，见系统提示的数据分域"},
    }, "required": ["id"]},
}

_CATALOG: dict[str, Any] = {
    "name": "catalog_search",
    "description": "检索 wmshare 数据目录：某个指标/接口有没有、确切码是什么"
                   "（先查目录再取数，零 EC 零网络）",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "关键词，如 股息率"},
    }, "required": ["query"]},
}


def build_system_prompt(skills: list[Skill]) -> str:
    """系统提示 = 铁律 + 每域一行卡片（全文按需 read_skill）。"""
    return _PROMPT_TMPL.format(domain_cards=domain_cards(skills))


def build_tools(skills: list[Skill]) -> list[dict[str, Any]]:
    """扁平工具面：清单条目按域序排列并加【域】前缀，再加两个宿主工具。"""
    display = {s.id: s.display_name for s in skills}
    order = {d: i for i, d in enumerate(DOMAIN_ORDER)}
    entries = sorted(executor.load_registry(),
                     key=lambda e: (order.get(e["domain"], 99), e["id"]))
    tools: list[dict[str, Any]] = []
    for entry in entries:
        tool = executor.to_llm_tools([entry])[0]
        name = display.get(entry["domain"], entry["domain"])
        tool["description"] = f"【{name}】{tool['description']}"
        tools.append(tool)
    tools.extend([dict(_READ_SKILL), dict(_CATALOG)])
    return tools


def make_execute_fn(ctx: Any, config: LLMConfig, ledger: SourceLedger,
                    skills: list[Skill]) -> Any:
    """执行闭包：宿主工具（技能/目录）+ 清单工具（预算闸 → 取数 → 入账）。"""
    by_id = {e["id"]: e for e in executor.load_registry()}
    skills_by_id = {s.id: s for s in skills}
    spent = {"ec": 0}

    def execute(name: str, args: dict[str, Any]) -> tuple[str, Any, int | None]:
        host = _host_tool(ctx, ledger, skills_by_id, name, args)
        if host is not None:
            return host
        return _data_tool(ctx, config, ledger, by_id, spent, name, args)

    return execute


# ------------------------------------------------------------------ 内部

def _host_tool(ctx: Any, ledger: SourceLedger, skills_by_id: dict[str, Skill],
               name: str, args: dict[str, Any]) -> tuple[str, Any, int | None] | None:
    """宿主工具（零 EC）；不是宿主工具返回 ``None`` 交给清单执行器。"""
    if name == "read_skill":
        skill = skills_by_id.get(str(args.get("id") or ""))
        if skill is None:
            return (f"没有领域 {args.get('id')!r}；"
                    f"可用：{sorted(skills_by_id)}"), None, 0
        return skill.body, None, 0
    if name == "catalog_search":
        return _do_catalog(ctx, ledger, str(args.get("query") or ""))
    return None


def _data_tool(ctx: Any, config: LLMConfig, ledger: SourceLedger,
               by_id: dict[str, dict[str, Any]], spent: dict[str, int],
               name: str, args: dict[str, Any]) -> tuple[str, Any, int | None]:
    """清单工具：预算闸 → 通用执行器取数 → 证据入账并加来源编号前缀。"""
    entry = by_id.get(name)
    if entry is None:
        return f"未知工具 {name}", None, None
    if not _budget_ok(ctx, config, spent, entry):
        return ("本轮 EC 预算已用尽：请基于已有数据作答，"
                "或明确告诉用户哪一步因预算没执行。"), None, 0
    try:
        text, evidence, as_of = executor.execute(ctx, entry, args)
    except Exception as exc:  # noqa: BLE001 - 工具失败给模型可读原因
        return f"工具 {name} 执行失败：{exc}", None, None
    n = ledger.add(kind=str(evidence["kind"]),
                   title=str(evidence["title"]),
                   detail=str(evidence.get("detail") or ""),
                   as_of=str(evidence.get("as_of") or ""))
    return ledger.prefix_for(n, str(evidence["title"]),
                             str(evidence.get("as_of") or "")) + text, evidence, None


def _do_catalog(ctx: Any, ledger: SourceLedger,
                query: str) -> tuple[str, Any, int | None]:
    if not query:
        return "catalog_search 需要 query", None, 0
    fn = getattr(getattr(ctx, "fetcher", None), "catalog_search", None)
    if not callable(fn):
        return "当前取数器不支持目录检索（未装 wmshare？）", None, 0
    try:
        rows = fn(query)
    except Exception as exc:  # noqa: BLE001 - 检索失败给模型可读原因
        return f"目录检索失败：{exc}", None, None
    n = ledger.add(kind="目录", title=f"数据目录检索「{query}」")
    text = _rows_or_empty(rows)
    return ledger.prefix_for(n, f"数据目录检索「{query}」", "") + text, None, 0


def _budget_ok(ctx: Any, config: LLMConfig, spent: dict[str, int],
               entry: dict[str, Any]) -> bool:
    """预算闸：预估值可得的条目，预估后超预算就不执行（省 EC 也诚实）。"""
    fetcher = getattr(ctx, "fetcher", None)
    target = entry.get("target") or ""
    est = {}
    if fetcher is not None and entry.get("kind") != "local":
        try:
            est = fetcher.cost_estimate(target) or {}
        except Exception:  # noqa: BLE001 - 估不出来按未知放行（事后仍计量）
            est = {}
    hi = est.get("ec_hi")
    if isinstance(hi, (int, float)) and spent["ec"] + int(hi) > config.max_ec:
        return False
    spent["ec"] += int(hi) if isinstance(hi, (int, float)) else 0
    return True


def _rows_or_empty(rows: Any) -> str:
    import json

    if not rows:
        return "（目录中没有检索到；换关键词再试，或如实告诉用户没有）"
    return json.dumps(rows[:8], ensure_ascii=False, default=str)
