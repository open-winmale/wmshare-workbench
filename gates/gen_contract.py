#!/usr/bin/env python3
"""生成前后端契约：``backend/workbench/core/envelope.py`` → ``frontend/src/api/contract.ts``。

**为什么生成而不是手写双份**：兄弟仓四个项目全是手写 ``types.ts`` 且零漂移检查；
其中 ``winmale-v2`` 为跨仓同步上了 proto submodule + 三仓提交。规模上（约 14 个端点）
不需要 OpenAPI codegen，但「手写双份 + 无检查」这个坑必须避开。

本脚本读三样：
1. ``ENVELOPE_FIELDS`` / ``FRESHNESS_VALUES`` / ``EC_FIELDS`` / ``ENVELOPE_VERSION``
2. ``ERROR_ACTIONS``（错误态按钮）
3. ``ENDPOINTS``（端点清单）

输出确定性（键排序、无时间戳），因此 ``check_contract.py`` 可以逐字节比对：
**手改 contract.ts 会红**，这是漂移门禁的工作前提。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate import FRONTEND, SRC, GateError  # noqa: E402

ENVELOPE_PY = SRC / "core" / "envelope.py"
OUT = FRONTEND / "src" / "api" / "contract.ts"

HEADER = """\
/**
 * 自动生成文件 —— 禁止手改。
 *
 * 真源：backend/workbench/core/envelope.py
 * 重新生成：make gen-contract
 * 漂移检查：gates/check_contract.py（CI 强制）
 *
 * 为什么生成：手写双份 TS 类型与后端契约必然漂移，且漂移只会在运行时
 * 表现为 undefined。见 docs/ADR/002。
 */

"""


def load_envelope():
    """按文件路径加载契约模块（不依赖安装状态）。"""
    name = "_wb_contract_src"
    spec = importlib.util.spec_from_file_location(name, ENVELOPE_PY)
    if spec is None or spec.loader is None:
        raise GateError(f"无法加载 {ENVELOPE_PY}")
    mod = importlib.util.module_from_spec(spec)
    # dataclass 解析注解时需要模块已在 sys.modules 里
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(name, None)
    return mod


def ts_union(name: str, values: tuple[str, ...]) -> str:
    """生成 ``export const X = [...] as const`` + 派生类型。

    派生类型名用 **PascalCase 单数**（``FRESHNESS_VALUES`` → ``FreshnessValue``）：
    TS 的类型命名约定是 PascalCase，而 ``name[:-1]`` 会得到 ``FRESHNESS_VALUE``，
    与引用处（``Envelope.freshness: FreshnessValue``）对不上——这就是生成物
    与手写引用脱节的典型形态，靠 ``make gen-contract`` + ``check_contract`` 兜住。
    """
    items = ", ".join(f'"{v}"' for v in values)
    singular = _pascal_singular(name)
    return (f"export const {name} = [{items}] as const;\n"
            f"export type {singular} = (typeof {name})[number];\n")


def _pascal_singular(const_name: str) -> str:
    """``FRESHNESS_VALUES`` → ``FreshnessValue``；``EC_FIELDS`` → ``EcField``。"""
    base = const_name[:-1] if const_name.endswith("S") else const_name
    return "".join(part.capitalize() for part in base.split("_"))


def render() -> str:
    mod = load_envelope()
    fields = tuple(mod.ENVELOPE_FIELDS)
    freshness = tuple(mod.FRESHNESS_VALUES)
    ec_fields = tuple(mod.EC_FIELDS)
    actions = tuple(mod.ERROR_ACTIONS)
    endpoints: dict[str, dict[str, str]] = dict(mod.ENDPOINTS)
    version = int(mod.ENVELOPE_VERSION)

    parts: list[str] = [HEADER]
    parts.append(f"export const ENVELOPE_VERSION = {version};\n\n")

    parts.append("//: 信封字段集（顺序即后端构造顺序）\n")
    parts.append(ts_union("ENVELOPE_FIELDS", fields))
    parts.append("\n")
    parts.append("//: 数据新鲜度档位\n")
    parts.append(ts_union("FRESHNESS_VALUES", freshness))
    parts.append("\n")
    parts.append("//: 失败时可采取的处置动作（决定错误态按钮）\n")
    parts.append(ts_union("ERROR_ACTIONS", actions))
    parts.append("\n")
    parts.append("//: ec 子结构字段\n")
    parts.append(ts_union("EC_FIELDS", ec_fields))
    parts.append("\n")

    parts.append("""\
export interface EcEstimate {
  /** 无成本模型时为 null —— **不是 0**（0 会被读成「免费」） */
  pred_lo: number | null;
  pred_hi: number | null;
  /** 实际消耗，来自后端 meta.metering */
  actual: number | null;
  /** 成本模型名；无模型时 "none" */
  model: string;
}

export interface Envelope<T = unknown> {
  ok: boolean;
  /** 数据截至日 YYYY-MM-DD；未知为 "" */
  as_of: string;
  /** 载荷。ok=false 时后端保证为 {}（失败原因在 meta） */
  data: T;
  meta: Record<string, unknown>;
  freshness: FreshnessValue;
  /** 中文告警，逐条可读 */
  warnings: string[];
  ec: EcEstimate | null;
}

/** 失败信封的 meta 约定字段 */
export interface ErrorMeta {
  error?: string;
  code?: string;
  action?: ErrorAction;
}

""")

    parts.append("//: 端点清单（前端不得手写端点字符串）\n")
    lines = ["export const ENDPOINTS = {"]
    for slug in sorted(endpoints):
        spec = endpoints[slug]
        summary = spec.get("summary", "")
        lines.append(f'  {slug}: {{ method: "{spec["method"]}", '
                     f'path: "{spec["path"]}", summary: "{summary}" }},')
    lines.append("} as const;\n")
    parts.append("\n".join(lines))
    parts.append("\nexport type EndpointSlug = keyof typeof ENDPOINTS;\n")
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check = "--check" in args
    text = render()
    if check:
        if not OUT.is_file():
            print(f"FAIL [contract] {OUT} 不存在；请跑 make gen-contract")
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print(f"FAIL [contract] {OUT} 与真源不一致；请跑 make gen-contract")
            return 1
        print(f"OK   [contract] {OUT.name} 与真源一致")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"OK   [contract] 已生成 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
