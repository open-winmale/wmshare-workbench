#!/usr/bin/env python3
"""门禁公共设施：基线读取、路径、结果收集。

所有门禁脚本共享同一套约定（``docs/PROJECT_SPEC.md`` §6）：

- 退出码 0 = 通过，1 = 有违规，2 = 门禁自身故障（基线缺失/格式错）。
- 违规必须**定位到文件:行**，否则无从修。
- 输出走 stdout，稳定可 grep（``FAIL`` / ``WARN`` / ``OK`` 前缀）。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: 仓库根（gates/ 的上一级）。所有门禁以此为锚，避免受 cwd 影响。
REPO = Path(__file__).resolve().parents[1]
BASELINES = REPO / "quality" / "baselines"
#: 后端包根。``backend/`` 自身即源布局隔离层，故不再套 ``src/``。
BACKEND = REPO / "backend"
#: 分层校验的扫描面。
SRC = BACKEND / "workbench"
#: 应用层工具目录——信封校验扫这里的 ``handler.py``。
#: 曾因与应用层 ``tools/`` 同名而扫错目录（扫到门禁脚本自身），改名 ``gates/`` 后物理可分。
APP_TOOLS = SRC / "tools"
GATES_DIR = REPO / "gates"
DOCS = REPO / "docs"
FRONTEND = REPO / "frontend"
#: 兼容旧名；新代码请用 ``FRONTEND``。
WEB = FRONTEND
TESTS = REPO / "tests"
#: 前端构建产物落点（gitignore，但在 package-data 里）。
STATIC = SRC / "static"


class GateError(RuntimeError):
    """门禁自身故障（不是代码违规）：基线缺失、JSON 非法、结构不符。"""


@dataclass
class Result:
    """一个门禁的运行结果。"""

    name: str
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def report(self) -> int:
        for w in self.warnings:
            print(f"WARN [{self.name}] {w}")
        for f in self.failures:
            print(f"FAIL [{self.name}] {f}")
        if self.failures:
            print(f"FAIL [{self.name}] {len(self.failures)} 处违规"
                  f"（检查 {self.checked} 项）")
            return 1
        print(f"OK   [{self.name}] 检查 {self.checked} 项"
              f"{f'，{len(self.warnings)} 处告警' if self.warnings else ''}")
        return 0


def load_baseline(name: str) -> dict:
    """读取 ``quality/baselines/<name>.json``；缺失或非法即门禁故障。"""
    path = BASELINES / f"{name}.json"
    if not path.is_file():
        raise GateError(f"基线缺失：{path.relative_to(REPO)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(f"基线 JSON 非法：{path.relative_to(REPO)}：{exc}") from exc
    if not isinstance(data, dict):
        raise GateError(f"基线必须是 JSON 对象：{path.relative_to(REPO)}")
    return data


def rel(path: Path) -> str:
    """相对仓库根的路径（便于定位与 grep）。"""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def run_gate(name: str, fn) -> int:
    """统一的入口包装：把 GateError 转成 exit 2，其余异常不吞。"""
    try:
        return fn().report()
    except GateError as exc:
        print(f"ERROR [{name}] {exc}", file=sys.stderr)
        return 2
