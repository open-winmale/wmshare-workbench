#!/usr/bin/env python3
"""门禁 6：组件清单与孤儿组件（``docs/PROJECT_SPEC.md`` §8.4）。

规则「≥2 个使用方才允许进 ``components/ui/``」如果没有检查手段，
就会变成「先进去，以后再找用处」。本脚本统计每个组件的实际引用数：

- ``--write``：重新生成 ``baselines/components.json``
- ``--check``：对照基线，发现**孤儿组件**（usage 为 0）即失败

计数口径：``<XxxYyy`` / ``<xxx-yyy`` 在其它文件中的出现次数，
排除组件自身定义文件与预览页（``dev/preview``）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate import BASELINES, FRONTEND, Result, rel, run_gate  # noqa: E402

BASELINE = BASELINES / "components.json"
#: 不计入 usage 的路径片段（自身定义、预览页、测试）
SKIP_PARTS = ("node_modules", "dev/preview", "tests", ".test.")


def component_files() -> list[Path]:
    ui = FRONTEND / "src" / "components"
    if not ui.is_dir():
        return []
    return sorted(p for p in ui.rglob("*.vue")
                  if not any(s in str(p) for s in SKIP_PARTS))


def pascal(name: str) -> str:
    """``kpi-strip`` → ``KpiStrip``；**已是 PascalCase 的原样返回**。

    上一版对 ``KpiStrip`` 也做 ``.capitalize()``，得到 ``Kpistrip``——
    于是所有驼峰命名的组件都被判成孤儿（模板标签匹配不到）。
    """
    if name[:1].isupper() and "_" not in name and "-" not in name:
        return name
    return "".join(part.capitalize() for part in re.split(r"[-_.]", name))


def kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def count_usage(target: Path, comp_name: str) -> int:
    """统计该组件的引用次数（排除自身与跳过项）。

    **两种引用形态都要算**：

    1. 模板标签：``<KpiStrip`` / ``<kpi-strip``
    2. ``<script setup>`` 里的 import：``import KpiStrip from './KpiStrip.vue'``

    上一版只匹配第 1 种。但 ``<script setup>`` 下组件的 PascalCase 标签
    **必须**来自 import，所以「import + 模板用」是主流写法；
    漏掉 import 等于把所有组件都误判成孤儿。
    """
    pascal_name = pascal(comp_name)
    pats = [
        re.compile(rf"<{re.escape(pascal_name)}\b"),
        re.compile(rf"<{re.escape(kebab(comp_name))}\b"),
        # import X from '.../X.vue'（含 `import X, { type Y } from` 形态）
        re.compile(rf"import\s+{re.escape(pascal_name)}\b[^'\"\n]*from\s+['\"][^'\"]*"
                   rf"{re.escape(comp_name)}\.vue['\"]"),
        # import { type X } from '.../X.vue'
        re.compile(rf"\{{\s*type\s+{re.escape(pascal_name)}\s*\}}\s*from\s+"
                   rf"['\"][^'\"]*{re.escape(comp_name)}\.vue['\"]"),
    ]
    total = 0
    root = FRONTEND / "src"
    for path in root.rglob("*"):
        if not path.is_file() or path == target:
            continue
        if any(s in str(path) for s in SKIP_PARTS):
            continue
        if path.suffix not in {".vue", ".ts", ".tsx", ".js"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pat in pats:
            total += len(pat.findall(text))
    return total


def scan() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for path in component_files():
        name = path.stem
        out[name] = {"file": rel(path), "usage": count_usage(path, name)}
    return out


def write_baseline(data: dict[str, dict[str, object]]) -> None:
    payload = {
        "_comment": "UI 组件清单与引用处数基线。孤儿组件（usage=0）即红。"
                    "由 tools/gen_component_index.py --write 生成/校验。",
        "version": 1,
        "components": data,
        "min_usage": 1,
        "notes": [
            "usage 计数：组件被 <XxxYyy /> 或 <xxx-yyy /> 引用的次数，"
            "不含自身定义与预览页。",
            "P0 阶段清单为空是正确状态；P1 落组件后用 --write 生成。",
        ],
    }
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"OK   [components] 已写入 {rel(BASELINE)}（{len(data)} 个组件）")


def main(check: bool) -> Result:
    result = Result("components")
    found = scan()
    if not check:
        write_baseline(found)
        return result

    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        result.fail(f"基线缺失：{rel(BASELINE)}；请先跑 --write")
        return result
    except json.JSONDecodeError as exc:
        result.fail(f"基线 JSON 非法：{exc}")
        return result

    declared: dict = baseline.get("components") or {}
    min_usage = int(baseline.get("min_usage") or 1)

    for name, info in sorted(found.items()):
        result.checked += 1
        usage = int(info["usage"])          # type: ignore[arg-type]
        if usage < min_usage:
            result.fail(f"{info['file']} 是孤儿组件（引用 {usage} 次，"
                        f"要求 ≥{min_usage}）；未达使用门槛请留在 feature 目录")
        if name not in declared:
            result.fail(f"{info['file']} 未登记在基线；请跑 --write 更新")

    for name in sorted(set(declared) - set(found)):
        result.warn(f"基线登记的组件已不存在：{name}（请跑 --write 清理）")
    return result


if __name__ == "__main__":
    mode_check = "--check" in sys.argv
    raise SystemExit(run_gate("components", lambda: main(mode_check)))
