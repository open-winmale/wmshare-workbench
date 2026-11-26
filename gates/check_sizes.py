#!/usr/bin/env python3
"""门禁 2：文件与函数体量棘轮（``docs/PROJECT_SPEC.md`` §3）。

棘轮的语义是「**不许变差**」，不是「必须达标」：

- 已登记文件：行数不得超过基线（可减小，不可增大）。
- 未登记文件：不得超过 ``limits`` 里的硬上限。
- ``py_file_exceptions`` 里的文件用更高上限（如 ``server.py`` 特许 600）。
- 函数体量超 ``limits.function`` 或圈复杂度超基线 → 违规。

单文件行数失控是最常见的腐化起点：一旦某个文件「什么都能改」，它就什么都改。
本门禁的作用是让「再加一点点」在 CI 上变成一件需要讨论的事。

圈复杂度用 McCabe 近似：``if/elif/for/while/and/or/except/with/assert/
三元表达式/comprehension if`` 各计 1，基数 1。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate import FRONTEND, SRC, Result, load_baseline, rel, run_gate  # noqa: E402


def count_complexity(node: ast.AST) -> int:
    """近似圈复杂度（基数 1）。"""
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While,
                              ast.ExceptHandler, ast.With, ast.AsyncWith,
                              ast.Assert, ast.IfExp)):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += len(child.values) - 1
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp,
                                ast.GeneratorExp)):
            score += len(child.generators)
    return score


def func_id(path: Path, name: str) -> str:
    return f"{rel(path)}::{name}"


def check_python(result: Result, sizes: dict, complexity: dict) -> None:
    limits = sizes.get("limits") or {}
    hard_py = int(limits.get("py_file") or 400)
    exceptions: dict[str, int] = dict(limits.get("py_file_exceptions") or {})
    baseline_sizes: dict[str, int] = dict(sizes.get("baseline") or {})
    max_func = int(limits.get("function") or 60)
    tool_cap = int(limits.get("tool_handler") or 300)

    max_cx = int(complexity.get("max_complexity") or 12)
    baseline_cx: dict[str, int] = dict(complexity.get("baseline") or {})

    seen: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        if "static" in path.parts:
            continue
        key = rel(path)
        seen.add(key)
        n = sum(1 for _ in path.read_text(encoding="utf-8").splitlines())
        result.checked += 1

        cap = exceptions.get(key, hard_py)
        # 工具 handler 有单独上限（规范 §3 声明了但上一版从未读取）
        if path.name == "handler.py" and "tools" in path.parts:
            cap = min(cap, tool_cap)
        base = baseline_sizes.get(key)
        if base is not None:
            if n > base:
                result.fail(f"{key} 行数 {n} 超过基线 {base}（棘轮只允许变小）")
            # 基线白送松弛也是问题：基线远高于实际时告警，逼人收紧
            elif base > n * 1.1 and base - n >= 5:
                result.warn(f"{key} 基线 {base} 比实际 {n} 高出 "
                            f"{base - n} 行，请收紧基线")
        elif n > cap:
            result.fail(f"{key} 行数 {n} 超过上限 {cap}")

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            result.fail(f"{key}:{exc.lineno} 语法错误：{exc.msg}")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fname = node.name
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            result.checked += 1
            if length > max_func:
                result.fail(f"{key}:{node.lineno} 函数 {fname} 长 {length} 行，"
                            f"超过上限 {max_func}")
            cx = count_complexity(node)
            fid = func_id(path, fname)
            b = baseline_cx.get(fid)
            if b is not None:
                if cx > b:
                    result.fail(f"{key}:{node.lineno} 函数 {fname} 复杂度 {cx} "
                                f"超过基线 {b}（棘轮只允许变小）")
            elif cx > max_cx:
                result.fail(f"{key}:{node.lineno} 函数 {fname} 复杂度 {cx}，"
                            f"超过上限 {max_cx}")

    for stale in sorted(set(baseline_sizes) - seen):
        result.warn(f"基线登记了不存在的文件：{stale}（请清理）")
    for stale in sorted(set(baseline_cx) - {f for f in baseline_cx if seen_prefix(f, seen)}):
        result.warn(f"复杂度基线登记了不存在的函数：{stale}（请清理）")


def seen_prefix(fid: str, seen: set[str]) -> bool:
    """复杂度基线 id 形如 ``path::func``，判断其文件是否仍存在。"""
    return fid.split("::", 1)[0] in seen


def check_frontend(result: Result, sizes: dict) -> None:
    """前端体量预算：``.vue``、composable、CSS 块。

    规范 §3 声明了四个前端上限，上一版只实现 ``.vue``，另三个从未被读取——
    这条门禁等于没有。本版全部实现。
    """
    limits = sizes.get("limits") or {}
    vue_cap = int(limits.get("vue_file") or 250)
    comp_cap = int(limits.get("composable") or 120)
    css_cap = int(limits.get("css_block") or 150)
    src = FRONTEND / "src"
    if not src.is_dir():
        return

    for path in sorted(src.rglob("*")):
        if not path.is_file() or "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        result.checked += 1
        n = len(text.splitlines())
        key = rel(path)

        if path.suffix == ".vue":
            if n > vue_cap:
                result.fail(f"{key} 行数 {n} 超过上限 {vue_cap}；请拆原子组件")
            # scoped style 块单独计量
            for i, block in enumerate(_style_blocks(text), 1):
                result.checked += 1
                if block > css_cap:
                    result.fail(f"{key} 第 {i} 个 <style> 块 {block} 行，"
                                f"超过上限 {css_cap}；请抽出或用工具类")
        elif path.suffix == ".ts" and "composables" in path.parts:
            if n > comp_cap:
                result.fail(f"{key} 行数 {n} 超过上限 {comp_cap}；"
                            f"请拆 composable")


def _style_blocks(text: str) -> list[int]:
    """返回每个 ``<style>`` 块的行数（不含标签行）。"""
    out: list[int] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if "<style" in lines[i]:
            start = i + 1
            while i < len(lines) and "</style>" not in lines[i]:
                i += 1
            out.append(max(0, i - start))
        i += 1
    return out


def main() -> Result:
    result = Result("sizes")
    sizes = load_baseline("sizes")
    complexity = load_baseline("complexity")
    check_python(result, sizes, complexity)
    check_frontend(result, sizes)
    return result


if __name__ == "__main__":
    raise SystemExit(run_gate("sizes", main))
