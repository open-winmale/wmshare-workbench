#!/usr/bin/env python3
"""门禁 7：契约漂移 + 版本三元同步（``docs/ARCHITECTURE.md`` §契约）。

三项检查，前两项是**防止前后端失同步**，第三项堵兄弟仓踩过的坑：

1. **契约漂移**：``frontend/src/api/contract.ts`` 必须与 ``gates/gen_contract.py``
   重新生成的结果**逐字节一致**。手改会红——这是「生成物不手改」的物理保证
   （兄弟仓 `wmshare` 用 ``gen_*.py --check`` 早就这么做，四个前端仓都没做）。
2. **契约与基线一致**：生成的字段集必须等于 ``baselines/envelope.json``。
3. **版本三元同步**：``pyproject.toml`` == ``workbench.__version__`` ==
   ``frontend/package.json``。``wmshare-tools`` 在这件事上漂移过一次
   （CHANGELOG 1.7.1 手记：「`web/package.json` 版本号停留在 1.6.0」）。
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_contract  # noqa: E402
from _gate import FRONTEND, REPO, SRC, Result, load_baseline, rel, run_gate  # noqa: E402

PYPROJECT = REPO / "pyproject.toml"
PKG_JSON = FRONTEND / "package.json"
INIT_PY = SRC / "__init__.py"


def check_drift(result: Result) -> None:
    """contract.ts 与真源逐字节一致。"""
    out = gen_contract.OUT
    result.checked += 1
    if not out.is_file():
        result.fail(f"{rel(out)} 不存在；请跑 `make gen-contract`")
        return
    expected = gen_contract.render()
    actual = out.read_text(encoding="utf-8")
    if actual != expected:
        result.fail(
            f"{rel(out)} 与真源不一致（契约漂移）。请跑 `make gen-contract`；"
            f"若你是手改了这个文件——它由 backend/workbench/core/envelope.py 生成，"
            f"改那边才对（见文件头注释）"
        )


def check_against_baseline(result: Result) -> None:
    """生成结果与 baselines/envelope.json 一致。"""
    baseline = load_baseline("envelope")
    mod = gen_contract.load_envelope()
    pairs = (
        ("ENVELOPE_FIELDS", tuple(mod.ENVELOPE_FIELDS), tuple(baseline.get("fields") or ())),
        (
            "FRESHNESS_VALUES",
            tuple(mod.FRESHNESS_VALUES),
            tuple(baseline.get("freshness_values") or ()),
        ),
        ("EC_FIELDS", tuple(mod.EC_FIELDS), tuple(baseline.get("ec_fields") or ())),
    )
    for name, code, base in pairs:
        result.checked += 1
        if code != base:
            result.fail(f"{name} 与 baselines/envelope.json 不一致：代码 {code} vs 基线 {base}")

    result.checked += 1
    if int(mod.ENVELOPE_VERSION) != int(baseline.get("envelope_version", -1)):
        result.fail("ENVELOPE_VERSION 与基线不一致")

    # ENDPOINTS 必须非空且形状正确（前端全靠它，空表等于没有契约）
    eps = dict(mod.ENDPOINTS)
    result.checked += 1
    if not eps:
        result.fail("ENDPOINTS 为空；前端将没有端点可用")
    for slug, spec in eps.items():
        result.checked += 1
        if not isinstance(spec, dict) or not spec.get("method") or not spec.get("path"):
            result.fail(f"ENDPOINTS['{slug}'] 缺少 method/path")
        elif not str(spec["path"]).startswith("/api/"):
            result.fail(f"ENDPOINTS['{slug}'].path 必须以 /api/ 开头：{spec['path']}")


def _version_from_pyproject() -> str | None:
    """读 pyproject 的版本。

    两种合法写法：字面 ``version = "x"``，或 ``dynamic = ["version"]`` +
    ``[tool.setuptools.dynamic] version = {attr = "workbench.__version__"}``。
    后者是单一来源（版本只写在 ``__init__.py``），此时本项返回 ``None`` 且
    不报错——真正的核对交给 ``__version__`` 与 ``package.json`` 两项，
    以及下面「dynamic 已声明时不得再写字面 version」的一致性断言。
    """
    try:
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    project = data.get("project") or {}
    literal = project.get("version")
    if isinstance(literal, str) and literal:
        return literal
    dynamic = project.get("dynamic") or []
    if "version" in dynamic:
        attr = ((data.get("tool") or {}).get("setuptools") or {}).get("dynamic") or {}
        spec = attr.get("version") or {}
        if isinstance(spec, dict) and spec.get("attr"):
            return None  # 版本由 __init__.py 提供，属合法配置
        return ""  # 声明了 dynamic 却没给来源 → 视为配置错误
    return ""


def _version_from_init() -> str | None:
    text = INIT_PY.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    return m.group(1) if m else None


def _version_from_pkg() -> str | None:
    if not PKG_JSON.is_file():
        return None
    try:
        data = json.loads(PKG_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "INVALID_JSON"
    return str(data.get("version") or "")


def check_versions(result: Result) -> None:
    """版本同步（``wmshare-tools`` 曾在此漂移）。

    ``py`` 为 ``None`` = pyproject 用 ``dynamic = ["version"]`` 指向
    ``workbench.__version__``，属**合法配置**（单一来源），此时以 ``init``
    为准与 ``package.json`` 比对；``py`` 为空串 = 配置缺失/写错，报错。
    """
    py = _version_from_pyproject()
    init = _version_from_init()
    pkg = _version_from_pkg()

    result.checked += 1
    if py == "":
        result.fail("pyproject.toml 缺少 [project] version（或 dynamic 声明不完整）")
    result.checked += 1
    if init is None:
        result.fail(f"{rel(INIT_PY)} 缺少 __version__")

    if pkg is None:
        result.warn("frontend/package.json 不存在；版本同步跳过（P5 落地后必须补齐）")
        return
    if pkg == "INVALID_JSON":
        result.fail("frontend/package.json 不是合法 JSON")
        return

    # py 为 None 时用 init 代表「项目版本」，避免把合法配置误判为冲突
    versions = {
        "pyproject.toml": py or init,
        "workbench.__version__": init,
        "frontend/package.json": pkg,
    }
    distinct = {v for v in versions.values() if v is not None}
    result.checked += 1
    if len(distinct) > 1:
        detail = "，".join(f"{k}={v}" for k, v in versions.items())
        result.fail(
            f"版本不一致（{detail}）；各处必须同步——"
            f"`wmshare-tools` 曾因此在 CHANGELOG 1.7.1 修过一次"
        )


def main() -> Result:
    result = Result("contract")
    check_drift(result)
    check_against_baseline(result)
    check_versions(result)
    return result


if __name__ == "__main__":
    raise SystemExit(run_gate("contract", main))
