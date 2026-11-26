"""通用工具执行器：消费 ``registry.json`` 清单，不硬编码任何工具。

**清单即契约**：每个条目声明 ``{id, domain, kind, target, params, cost,
evidence, guards}``——新增 wmshare 能力 = 加一条 JSON 条目；
``tests/test_assistant_registry.py`` 负责校验 target 真实存在（防编造）。

**所有取数都经 ``_shared.fetch``**（hub 缓存 + 单飞 + last-known-good）——
这是「不烧配额」的全部依据，助手不得绕过。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .._shared import ToolError, apply_guards, as_of_of, fetch, non_negative_guards

__all__ = ["load_registry", "tools_for_domain", "to_llm_tools",
           "validate_arguments", "execute"]

_REGISTRY_PATH = Path(__file__).resolve().parent / "registry.json"
_registry_cache: list[dict[str, Any]] | None = None

#: 交给模型的结果截断口径（行数与字符数）——大结果截尾并如实注明，
#: 「喂全量」会稀释注意力也烧 token。
MAX_ROWS_SHOWN = 10
MAX_TEXT_CHARS = 4_000

_COST_HINTS = {"auto": "", "local": "",
               "medium": "（常规成本）",
               "high": "（昂贵！确认必要再调用）"}

#: 清单类型（沿用 wmshare 目录的 int/str 惯用名）→ JSON Schema 标准类型。
#: **必须映射**：部分供应商（智谱实测 2026-11-27，code 1210）严格校验
#: 工具 schema，``"int"`` 不是合法类型会整请求 400。
_JSON_TYPES = {"int": "integer", "float": "number", "number": "number",
               "str": "string", "string": "string", "bool": "boolean",
               "boolean": "boolean", "array": "array", "object": "object"}


def load_registry() -> list[dict[str, Any]]:
    """读工具清单（模块级缓存；清单是打包内静态文件）。"""
    global _registry_cache
    if _registry_cache is None:
        raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        _registry_cache = list(raw.get("tools") or [])
    return _registry_cache


def tools_for_domain(domain: str) -> list[dict[str, Any]]:
    return [t for t in load_registry() if t.get("domain") == domain]


def to_llm_tools(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清单条目 → OpenAI function 形状（name/description/parameters）。"""
    out = []
    for entry in entries:
        props: dict[str, Any] = {}
        required: list[str] = []
        for p in entry.get("params") or []:
            props[p["name"]] = {
                "type": _JSON_TYPES.get(p["type"], "string"),
                "description": p.get("desc", "")}
            if p.get("required"):
                required.append(p["name"])
        out.append({
            "name": entry["id"],
            "description": (entry.get("description") or "")
                            + _COST_HINTS.get(entry.get("cost") or "auto", ""),
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        })
    return out


def validate_arguments(entry: dict[str, Any],
                       args: dict[str, Any]) -> dict[str, Any]:
    """按清单校验/收敛参数：缺必填报错、类型收敛、多余键丢弃。

    模型给的参数不可信（会漏 required、把 int 写成 str）——在宿主侧
    统一收敛，而不是让上游收到脏参数后报天书。
    """
    out: dict[str, Any] = {}
    for p in entry.get("params") or []:
        name, ptype = p["name"], p["type"]
        value = args.get(name)
        if value is None or value == "":
            if p.get("required"):
                raise ToolError(f"{entry['id']} 缺少必填参数 {name}",
                                code="missing_param")
            if p.get("default") is not None:
                out[name] = p["default"]
            continue
        out[name] = _coerce(entry["id"], name, ptype, value)
    return out


def execute(ctx: Any, entry: dict[str, Any], args: dict[str, Any],
            *, force: bool = False) -> tuple[str, dict[str, Any], str]:
    """执行一个清单条目，返回 ``(给模型的文本, 证据, as_of)``。

    ``call``/``facade`` 走 hub 取数；``local`` 读本地库（零 EC）。
    ``guards: true`` 的条目（选股）自动追加非负守卫——与选股页同口径。
    """
    kind = entry.get("kind")
    if kind == "local":
        return _execute_local(ctx, entry)
    params = validate_arguments(entry, args)
    if entry.get("guards") and isinstance(params.get("where"), str):
        where = params["where"]
        guards = non_negative_guards(where, str(params.get("order") or ""))
        params["where"] = apply_guards(where, guards)
    target = entry["target"]
    if kind == "facade":
        value, as_of = fetch(ctx, target, params,
                             facade=(entry["ns"], entry["method"]), force=force)
    else:
        value, as_of = fetch(ctx, target, params, force=force)
    as_of = as_of or as_of_of(value) or _rows_as_of(value)
    text = _compact(value, int(entry.get("max_rows") or MAX_ROWS_SHOWN))
    evidence = {
        "kind": entry.get("evidence") or "数据",
        "title": f"{entry['title']} · {_brief_params(params)}",
        "detail": f"{target}",
        "as_of": as_of,
    }
    return text, evidence, as_of


# --------------------------------------------------------------------- 内部

def _execute_local(ctx: Any, entry: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    """本地只读工具（自选/持仓档案名）。经 ``ctx.store``，零 EC 零网络。"""
    store = getattr(ctx, "store", None)
    if store is None:
        raise ToolError("本地存储未初始化", code="internal", action="report")
    if entry["target"] == "local.watchlist":
        rows = store.list_watch()
        text = _compact(rows) if rows else "（自选清单为空）"
    elif entry["target"] == "local.positions":
        names = store.list_position_sets()
        text = ("、".join(names) if names else "（没有持仓档案）")
    else:  # pragma: no cover - 清单守卫会拦未知 local target
        raise ToolError(f"未知本地工具 {entry['target']}", code="param")
    evidence = {"kind": "本地", "title": entry["title"],
                "detail": entry["target"], "as_of": ""}
    return text, evidence, ""


def _coerce(tool: str, name: str, ptype: str, value: Any) -> Any:
    """把模型的参数值收敛到清单声明的类型。"""
    if ptype == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ToolError(f"{tool}.{name} 必须是整数，收到 {value!r}",
                            code="param") from None
    if ptype == "boolean":
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "true", "yes")
    if ptype == "array":
        if isinstance(value, list):
            return value
        return [v.strip() for v in str(value).split(",") if v.strip()]
    return str(value)


def _compact(value: Any, max_rows: int = MAX_ROWS_SHOWN) -> str:
    """结果压缩：行表按时间方向取窗口 + 如实注明截断；dict 转有限长度 JSON。

    时间升序的行表（日 K / 分红明细 / 估值长表）取**最近** N 行——取最旧
    N 行会让「最近走势/最近分红」答成几年前的旧数据。非时间序列（榜单/
    直方图）仍取前 N 行。条目可用 ``max_rows`` 声明更宽的窗口。
    """
    rows = _as_rows(value)
    if rows is not None:
        total = len(rows)
        text = json.dumps(_window(rows, max_rows), ensure_ascii=False, default=str)
        if total > max_rows:
            where = "最近" if _dates_ascending(rows) else "前"
            text += (f"\n（共 {total} 行，仅展示{where} {max_rows} 行；"
                     f"需要更多请缩小范围再取）")
        return text
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "…（结果过长已截断；请缩小查询范围）"
    return text


def _window(rows: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    return rows[-max_rows:] if _dates_ascending(rows) else rows[:max_rows]


_DATE_KEYS = ("date", "trade_date", "ex_date", "pay_date", "announce_date",
              "sas", "period")


def _rows_as_of(value: Any) -> str:
    """行表截至日：末行日期列（DataFrame 也走 ``to_dict`` 鸭子探测）。"""
    rows = _as_rows(value)
    if not rows:
        return ""
    key = next((k for k in _DATE_KEYS if rows[-1].get(k)), None)
    return str(rows[-1].get(key) or "")[:10] if key else ""


def _dates_ascending(rows: list[dict[str, Any]]) -> bool:
    """首行有日期键且末行日期严格更晚 → 按时间升序（取尾部窗口）。"""
    if not rows:
        return False
    key = next((k for k in _DATE_KEYS if rows[0].get(k)), None)
    if key is None:
        return False
    first, last = str(rows[0].get(key)), str(rows[-1].get(key))
    return bool(first and last and last > first)


def _as_rows(value: Any) -> list[dict[str, Any]] | None:
    """行表探测（list[dict] / DataFrame / 信封 data.rows），否则 None。"""
    records = _maybe_records(value)
    if records is not None:
        return [r for r in records if isinstance(r, dict)]
    if isinstance(value, list) and (not value or isinstance(value[0], dict)):
        return [r for r in value if isinstance(r, dict)]
    return _envelope_rows(value)


def _maybe_records(value: Any) -> list | None:
    """DataFrame 鸭子探测（``to_dict("records")``），不 import pandas。"""
    to_records = getattr(value, "to_dict", None)
    if not callable(to_records):
        return None
    try:
        records = to_records("records")
    except (TypeError, ValueError):
        return None
    return records if isinstance(records, list) else None


def _envelope_rows(value: Any) -> list[dict[str, Any]] | None:
    """统一信封里的 ``data.rows``（组合门面惯用形状）。"""
    if not isinstance(value, dict):
        return None
    data = value.get("data")
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [r for r in _as_rows(data["rows"]) or []]
    return None


def _brief_params(params: dict[str, Any]) -> str:
    parts = []
    for key, value in params.items():
        text = str(value)
        parts.append(f"{key}={text[:24]}")
    return " ".join(parts) if parts else "-"
