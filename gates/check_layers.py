#!/usr/bin/env python3
"""门禁 1：跨层依赖方向（``docs/PROJECT_SPEC.md`` §2）。

**前后端两套独立层次，一个契约边界。** 跨边界不得 import——只能走 HTTP JSON，
契约由 ``gates/gen_contract.py`` 生成到 ``frontend/src/api/contract.ts``。

深度语义统一为 **数字越小越深**（``core: 0`` 最深）：

| 后端 depth | 层 | 前端 depth | 层 |
|---|---|---|---|
| 0 | `core` | 0 | `api` |
| 1 | `platform` | 1 | `components` |
| 2 | `client` | 2 | `composables` |
| 3 | `tools` | 3 | `features` |

**判定顺序很重要**（这是上一版的 bug 所在）：

1. 先查白名单。**在白名单里 → 放行**，不再做方向判断。
   上一版先判方向后查白名单，而 ``depth[dst] < depth[src]`` 被当成「反向」，
   于是每一条合法的向下边（如 ``client→core``）都被误判为反向，
   「未登记边」分支成了死代码。
2. 不在白名单 → 若 ``depth[dst] > depth[src]`` 报「反向依赖」（更具体的诊断）。
3. 否则报「未登记跨层依赖」。

**历史教训**：这个门禁在修复前从未真正工作过——仓库里零跨层 import，
所以 ``scanned == 2``、永远绿。这正是「门禁必须配注入测试」的理由。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate import FRONTEND, SRC, GateError, Result, load_baseline, rel, run_gate  # noqa: E402

#: 后端子包 → 层名。
BACKEND_DIRS: dict[str, str] = {
    "core": "core",
    "platform": "platform",
    "client": "client",
    "tools": "tools",
}

#: 前端 ``src/`` 子目录 → 层名。
FRONTEND_DIRS: dict[str, str] = {
    "api": "api",
    "components": "components",
    "composables": "composables",
    "features": "features",
}

#: 前端 import 说明符：``@/x`` / ``../x`` / ``./x``。
FE_IMPORT = re.compile(
    r"""(?:from\s+|import\s+)\(?\s*['"](@/[^'"]+|\.\.?/[^'"]+)['"]""")

#: ``tools/`` 下**不是工具**的共用模块——「工具之间零耦合」的唯一例外。
#:
#: 规则本意是「工具之间零耦合」，而 ``_shared`` 是所有工具共用的基础设施
#: （取数 + 信封 + 错误分级），不属于任何单个工具。九个 handler 各写一遍
#: 同一套错误分级，最先漂移的就是 ``QuotaError`` → ``topup`` 这条映射。
#:
#: 用**精确名单**而非前缀匹配：新增第二个共用模块必须改这里，
#: 让「又多了一个共用件」成为一次可见的架构决策，而不是悄悄扩散。
SHARED_TOOL_MODULES: frozenset[str] = frozenset({"_shared"})


# --------------------------------------------------------------------------
# 后端
# --------------------------------------------------------------------------

def backend_layer_of(path: Path) -> str | None:
    """路径 → 后端层名。

    深度 1 的顶层模块（``__main__.py`` / ``bootstrap.py``）归 ``bootstrap`` 层
    ——**组合根**：装配 registry、注入依赖，是唯一允许 import ``tools`` 的地方。

    上一版把它们归 ``platform``，结果是「谁都不许 import tools」，
    服务层拿不到 handler；上一版的上一版干脆 ``return None`` 让它们免检。
    组合根是一个正当的架构概念，不该靠豁免实现。
    """
    try:
        parts = path.relative_to(SRC).parts
    except ValueError:
        return None
    if len(parts) == 1:
        return "bootstrap" if path.suffix == ".py" else None
    return BACKEND_DIRS.get(parts[0])


def resolve_relative(path: Path, node: ast.ImportFrom) -> str | None:
    """把 ``from ..client import hub`` 解析成绝对模块串。

    ``ast.ImportFrom.level`` 是相对级数（1 = 同级，2 = 上一级…）。
    上一版 ``if node.level: continue`` 直接跳过，导致 core 里的
    ``from ..client import x`` 完全隐形——这是最危险的漏检：
    想绕过分层检查，写相对 import 就行。
    """
    if not node.level:
        return node.module
    try:
        base = path.relative_to(SRC).parent
    except ValueError:
        return None
    for _ in range(node.level - 1):
        base = base.parent
    parts = list(base.parts)
    if node.module:
        parts.extend(node.module.split("."))
    return "workbench." + ".".join(parts)


def imported_modules(path: Path, tree: ast.AST) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = resolve_relative(path, node)
            if module:
                out.append((module, node.lineno))
    return out


def backend_layer_of_module(module: str) -> str | None:
    """``workbench.client.hub`` → ``client``。

    注意段数：``workbench.client`` 只有 2 段（``from workbench.client import hub``
    的常见写法），必须能识别；少于 2 段（仅 ``workbench``）才返回 None。
    """
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "workbench":
        return None
    return BACKEND_DIRS.get(parts[1])


def check_backend(result: Result, cfg: dict) -> None:
    depth: dict[str, int] = dict(cfg.get("depth") or {})
    allowed = {(str(a), str(b)) for a, b in cfg.get("allowed_edges") or []}
    if not depth:
        raise GateError("baselines/imports.json 缺少 backend.depth")

    scanned = 0
    for path in sorted(SRC.rglob("*.py")):
        if "static" in path.parts:
            continue
        src_layer = backend_layer_of(path)
        if src_layer is None:
            continue
        scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            result.fail(f"{rel(path)}:{exc.lineno} 语法错误：{exc.msg}")
            continue

        mods = imported_modules(path, tree)
        for module, lineno in mods:
            dst = backend_layer_of_module(module)
            if dst is None or dst == src_layer:
                continue
            result.checked += 1
            loc = f"{rel(path)}:{lineno}"

            if src_layer == "core":
                result.fail(f"{loc} core 是叶子层，不得 import {module}")
                continue
            # ① 白名单优先放行——顺序不能反
            if (src_layer, dst) in allowed:
                continue
            # ② 反向依赖（更具体的诊断）
            if depth.get(dst, -1) > depth.get(src_layer, -1):
                result.fail(f"{loc} 反向依赖：{src_layer}(depth {depth.get(src_layer)}) "
                            f"→ {dst}(depth {depth.get(dst)})；只允许向下或同层")
                continue
            # ③ 向下/同层但未登记
            result.fail(f"{loc} 未登记的跨层依赖：{src_layer} → {dst}（{module}）；"
                        f"如需保留，请登记 quality/baselines/imports.json")

        # 工具之间禁止横向 import（用映射后的层判定，不再匹配字面量）
        if src_layer == "tools":
            try:
                mine = path.relative_to(SRC).parts[1]
            except (ValueError, IndexError):
                mine = None
            # 共用模块不属于任何工具：它 import 谁都不构成「横向耦合」
            if mine not in SHARED_TOOL_MODULES:
                for module, lineno in mods:
                    mp = module.split(".")
                    # workbench.tools.<other>... 只需 3 段：
                    # ``from workbench.tools.b import handler`` 的 module 是
                    # "workbench.tools.b"，旧条件要求 ≥4 段因而漏检。
                    if len(mp) >= 3 and mp[0] == "workbench" and mp[1] == "tools" \
                            and mine and mp[2] != mine \
                            and mp[2] not in SHARED_TOOL_MODULES:
                        result.fail(f"{rel(path)}:{lineno} 工具横向依赖："
                                    f"{mine} → {mp[2]}；工具之间必须零耦合")
    result.checked += scanned


# --------------------------------------------------------------------------
# 前端
# --------------------------------------------------------------------------

def frontend_layer_of(path: Path) -> str | None:
    """路径 → 前端层名。

    ``src/`` 顶层文件（``main.ts`` / ``App.vue``）是**应用入口/组合根**，
    与后端 ``bootstrap`` 同性质：它必须 import 各层来装配外壳。
    归 ``api``（最浅层）是错的——那会让入口无权 import ``features``，
    而装配正是它的职责。

    故入口不参与分层校验（返回 ``None``）。这与后端把 bootstrap 单列成层
    是同一条原则的两种实现：后端需要它被校验（防它偷做业务），
    前端入口只是 new Vue + import 组件，多一层校验收益为零。
    """
    try:
        parts = path.relative_to(FRONTEND / "src").parts
    except ValueError:
        return None
    if len(parts) == 1:
        return None         # src/ 顶层 = 应用入口，不参与分层
    return FRONTEND_DIRS.get(parts[0])


def resolve_frontend_import(path: Path, spec: str) -> str | None:
    """``@/components/ui/X`` / ``../components/X`` → 层名。"""
    if spec.startswith("@/"):
        target = spec[2:]
    else:
        try:
            base = path.relative_to(FRONTEND / "src").parent
        except ValueError:
            return None
        target = (base / spec).as_posix()
    target = target.lstrip("./")
    return FRONTEND_DIRS.get(target.split("/", 1)[0])


def check_frontend(result: Result, cfg: dict) -> None:
    """前端依赖方向 + 「唯一 fetch 出口」。

    上一版只查 ``.vue`` 里的 ``fetch(``，且在 ``web/`` 缺失时直接 return，
    而 PROJECT_SPEC 却声称它「解析 Vue 的 ``@/`` 别名引用」——那条声明是假的。
    本版真的解析 import 说明符，并覆盖 ``.ts`` / ``.vue``。
    """
    src = FRONTEND / "src"
    if not src.is_dir():
        return
    depth: dict[str, int] = dict(cfg.get("depth") or {})
    allowed = {(str(a), str(b)) for a, b in cfg.get("allowed_edges") or []}
    if not depth:
        raise GateError("baselines/imports.json 缺少 frontend.depth")

    scanned = 0
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".vue"}:
            continue
        if "node_modules" in path.parts:
            continue
        src_layer = frontend_layer_of(path)
        if src_layer is None:
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel_parts = path.relative_to(src).parts
        mine = rel_parts[1] if len(rel_parts) > 2 else None

        for lineno, line in enumerate(text.splitlines(), 1):
            for m in FE_IMPORT.finditer(line):
                spec = m.group(1)
                dst = resolve_frontend_import(path, spec)
                target_parts = spec.replace("@/", "").lstrip("./").split("/")

                # 工具横向耦合
                if src_layer == "features" and len(target_parts) >= 3 \
                        and target_parts[0] == "features" and mine \
                        and target_parts[1] != mine:
                    result.fail(f"{rel(path)}:{lineno} 工具横向依赖："
                                f"{mine} → {target_parts[1]}")

                if dst is None or dst == src_layer:
                    continue
                result.checked += 1
                loc = f"{rel(path)}:{lineno}"
                if (src_layer, dst) in allowed:
                    continue
                if depth.get(dst, -1) > depth.get(src_layer, -1):
                    result.fail(f"{loc} 前端反向依赖：{src_layer} → {dst}；"
                                f"只允许向下或同层")
                    continue
                result.fail(f"{loc} 未登记的前端跨层依赖：{src_layer} → {dst}")

        # fetch 只许出现在 api/
        if src_layer != "api":
            for lineno, line in enumerate(text.splitlines(), 1):
                if re.search(r"(?<![\w.])fetch\s*\(", line):
                    result.fail(f"{rel(path)}:{lineno} fetch 只能在 api/ 层；"
                                f"请经 frontend/src/api/ 统一出口")
    result.checked += scanned


def main() -> Result:
    result = Result("layers")
    baseline = load_baseline("imports")
    if int(baseline.get("version", 0)) < 2:
        raise GateError("baselines/imports.json 需为 version 2（前后端双套层次）")
    check_backend(result, baseline.get("backend") or {})
    check_frontend(result, baseline.get("frontend") or {})
    return result


if __name__ == "__main__":
    raise SystemExit(run_gate("layers", main))
