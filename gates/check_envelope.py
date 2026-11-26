#!/usr/bin/env python3
"""门禁 4：信封契约一致性（``docs/ENVELOPE.md``）。

四条校验，全部对准同一个失败模式——**信封随工具各自演化**：

1. **代码 ↔ 基线**：``core/envelope.py`` 的 ``ENVELOPE_FIELDS`` 必须与
   ``baselines/envelope.json`` 的 ``fields`` 完全一致（顺序也一致）。
2. **基线内部一致**：``required_fields`` ⊆ ``fields``；``ec_fields`` 与代码一致。
3. **handler 无野字段**：``tools/*/handler.py`` 里出现的信封字面量键集必须 ⊆ 契约键集。
   这拦住「我在这个面板里多加了个 retry_hint」这类局部发明。
4. **两条硬约束**：
   - ``ok=False``（或 ``ok_envelope`` 的失败分支）时 ``data`` 必须为 ``{}``；
   - 无成本模型时 ``ec`` 不得写 ``0`` 冒充「免费」。

另外附带扫描 ``except Exception: pass``——它在 ``PROJECT_SPEC`` §4 被列为禁止，
而这类吞异常最容易出现在取数层，正好与信封检查同源。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate import APP_TOOLS, SRC, Result, load_baseline, rel, run_gate  # noqa: E402

ENVELOPE_PY = SRC / "core" / "envelope.py"


def load_envelope_module():
    """直接按文件加载 ``core/envelope.py``（避免依赖安装状态）。

    必须先把模块注册进 ``sys.modules`` 再执行：``@dataclass`` 在解析注解时
    需要 ``sys.modules[cls.__module__]`` 存在，否则抛
    ``AttributeError: 'NoneType' object has no attribute '__dict__'``。
    """
    name = "_wb_envelope"
    spec = importlib.util.spec_from_file_location(name, ENVELOPE_PY)
    if spec is None or spec.loader is None:
        from _gate import GateError
        raise GateError(f"无法加载 {rel(ENVELOPE_PY)}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(name, None)
    return mod


def check_code_matches_baseline(result: Result, baseline: dict) -> set[str]:
    mod = load_envelope_module()
    code_fields = tuple(getattr(mod, "ENVELOPE_FIELDS", ()))
    base_fields = tuple(baseline.get("fields") or ())
    result.checked += 1

    if not code_fields:
        result.fail(f"{rel(ENVELOPE_PY)} 未声明 ENVELOPE_FIELDS")
        return set()
    if code_fields != base_fields:
        result.fail(
            f"信封字段不一致：代码 {code_fields} vs 基线 {base_fields}；"
            f"改契约须同步 docs/ENVELOPE.md 并在 baseline.changelog 记 ADR")
    if int(getattr(mod, "ENVELOPE_VERSION", -1)) != int(
            baseline.get("envelope_version", -2)):
        result.fail("信封版本号不一致：代码 "
                    f"{getattr(mod, 'ENVELOPE_VERSION', None)} vs 基线 "
                    f"{baseline.get('envelope_version')}")

    freshness = tuple(getattr(mod, "FRESHNESS_VALUES", ()))
    if list(freshness) != list(baseline.get("freshness_values") or []):
        result.fail(f"freshness 取值不一致：代码 {freshness} vs 基线 "
                    f"{baseline.get('freshness_values')}")

    ec_fields = tuple(getattr(mod, "EC_FIELDS", ()))
    if list(ec_fields) != list(baseline.get("ec_fields") or []):
        result.fail(f"ec 字段不一致：代码 {ec_fields} vs 基线 "
                    f"{baseline.get('ec_fields')}")
    return set(code_fields)


def handler_files() -> list[Path]:
    """应用层 handler——``backend/workbench/tools/<name>/handler.py``。

    上一版扫的是 ``repo/tools/``（门禁脚本目录），真实 handler 落地后
    **完全不会被检查**。改成应用层目录后才有意义。
    """
    if not APP_TOOLS.is_dir():
        return []
    return sorted(p for p in APP_TOOLS.rglob("handler.py"))


def literal_keys(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Dict):
        return {k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return set()


def check_handlers(result: Result, contract: set[str]) -> None:
    """handler 内信封字面量的键集必须是契约子集。"""
    for path in handler_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            result.fail(f"{rel(path)}:{exc.lineno} 语法错误：{exc.msg}")
            continue
        for node in ast.walk(tree):
            keys = literal_keys(node)
            if not keys:
                continue
            # 只关心「看起来像信封」的字面量：含 ok 且含 data
            if "ok" in keys and "data" in keys:
                result.checked += 1
                extra = keys - contract
                if extra:
                    result.fail(
                        f"{rel(path)}:{getattr(node, 'lineno', '?')} 信封出现"
                        f"契约外字段 {sorted(extra)}；契约字段为 {sorted(contract)}")


def check_hard_rules(result: Result) -> None:
    """两条硬约束的源码扫描 + 吞异常扫描。"""
    targets = [ENVELOPE_PY]
    if APP_TOOLS.is_dir():
        targets.extend(sorted(APP_TOOLS.rglob("*.py")))
    if SRC.is_dir():
        targets.extend(sorted(SRC.rglob("*.py")))

    seen: set[Path] = set()
    for path in targets:
        if path in seen:
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError):
            continue
        lines = text.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = literal_keys(node)
            # 硬约束 2：无成本模型不得写 0
            if "pred_lo" in keys or "pred_hi" in keys:
                result.checked += 1
                for k, v in zip(node.keys, node.values):
                    if not isinstance(k, ast.Constant):
                        continue
                    if k.value in ("pred_lo", "pred_hi") \
                            and isinstance(v, ast.Constant) and v.value == 0:
                        result.fail(
                            f"{rel(path)}:{getattr(node, 'lineno', '?')} "
                            f"ec.{k.value} 写了 0；无成本模型应为 None"
                            f"（0 会被读成「免费」）")

        # 硬约束 1：ok=False 的组合里 data 不得非空
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
            if fname != "build":
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            ok_node = kw.get("ok")
            if not (isinstance(ok_node, ast.Constant) and ok_node.value is False):
                continue
            result.checked += 1
            data_node = kw.get("data")
            if data_node is None:
                continue
            if not (isinstance(data_node, ast.Dict) and not data_node.keys):
                result.fail(
                    f"{rel(path)}:{node.lineno} build(ok=False) 的 data 非空；"
                    f"失败原因请放 meta")

        # 禁止吞异常
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("except") and stripped.endswith("pass"):
                result.fail(f"{rel(path)}:{i} 禁止 except ...: pass；"
                            f"请捕获具体异常并记日志")
            elif stripped == "except Exception:" and i < len(lines):
                nxt = lines[i].strip() if i < len(lines) else ""
                if nxt == "pass":
                    result.fail(f"{rel(path)}:{i + 1} 禁止 except Exception: pass")


def main() -> Result:
    result = Result("envelope")
    baseline = load_baseline("envelope")

    required = set(baseline.get("required_fields") or [])
    fields = set(baseline.get("fields") or [])
    if not required <= fields:
        result.fail(f"基线自相矛盾：required_fields 不在 fields 内："
                    f"{sorted(required - fields)}")
    result.checked += 1

    contract = check_code_matches_baseline(result, baseline) or fields
    check_handlers(result, contract)
    check_hard_rules(result)
    return result


if __name__ == "__main__":
    raise SystemExit(run_gate("envelope", main))
