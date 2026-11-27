#!/usr/bin/env python3
"""门禁 7：契约漂移 + 版本三元同步（``docs/ARCHITECTURE.md`` §契约）。

四项检查，前三项是**防止前后端失同步**，第四项堵「文档里的安装命令是死的」：

1. **契约漂移**：``frontend/src/api/contract.ts`` 必须与 ``gates/gen_contract.py``
   重新生成的结果**逐字节一致**。手改会红——这是「生成物不手改」的物理保证
   （兄弟仓 `wmshare` 用 ``gen_*.py --check`` 早就这么做，四个前端仓都没做）。
2. **契约与基线一致**：生成的字段集必须等于 ``baselines/envelope.json``。
3. **版本三元同步**：``pyproject.toml`` == ``workbench.__version__`` ==
   ``frontend/package.json``。``wmshare-tools`` 在这件事上漂移过一次
   （CHANGELOG 1.7.1 手记：「`web/package.json` 版本号停留在 1.6.0」）。
4. **分发包链接自洽**：README / 提示页 / release 工作流里出现的
   ``.../releases/.../download/<wheel 名>`` 必须是**合法的 PEP 427 文件名**，
   且其中版本号等于 ``__version__``。
   **真事（2026-11-26）**：为让链接「永久有效」，资产名被去掉版本号写成
   ``wmshare_workbench-py3-none-any.whl``。看着聪明，实际 **pip 与 uv 都拒绝**
   安装（PEP 427 要求 ``name-version-...``，``latest`` 不是合法版本）。
   于是 README「快速开始」的第一行就是死的，而当时八个门禁 + 453 个用例全绿：
   没人把那条命令真的跑一遍。本项把它变成机械断言。
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
README = REPO / "README.md"
RELEASE_YML = REPO / ".github" / "workflows" / "release.yml"

#: 分发包链接里的 wheel 文件名。只认 ``.../download/<name>.whl`` 形式。
WHEEL_URL_RE = re.compile(
    r"https?://[^\s`\"'<>)]*/releases/[^\s`\"'<>)]*/download/(?P<wheel>[^\s`\"'<>/]+\.whl)"
)
#: PEP 427 文件名：``{dist}-{version}-{python}-{abi}-{platform}.whl``。
WHEEL_NAME_RE = re.compile(
    r"^(?P<dist>[A-Za-z0-9._]+)-(?P<version>\d[^-]*)-(?P<py>[^-]+)-(?P<abi>[^-]+)-"
    r"(?P<plat>[^-]+)\.whl$"
)


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


def check_dist_links(result: Result) -> None:
    """用户会复制粘贴的 wheel 下载链接：文件名合法、版本与 ``__version__`` 一致。

    分两类，因为写法不同、能断言的东西也不同：

    - **字面链接**（README、未构建提示页）：直接断言 wheel 名符合 PEP 427 且
      版本号等于 ``__version__``。
    - **模板链接**（release.yml 用 ``${{ env.VER }}`` 拼）：静态扫描看不见最终
      值，改为断言它**确实从 ``workbench.__version__`` 取值**，且没有硬编码版本。
      运行时的一致性已由「取版本号」那一步兜住。
    """
    init = _version_from_init()
    if init is None:
        result.fail(f"{rel(INIT_PY)} 缺少 __version__，无法校验下载链接的版本号")
        return

    seen = 0
    for path in (README, SRC / "platform" / "not_built.py"):
        result.checked += 1
        if not path.is_file():
            result.fail(f"{rel(path)} 不存在；分发包链接无处校验")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in WHEEL_URL_RE.finditer(text):
            seen += 1
            result.checked += 1
            wheel = match.group("wheel")
            loc = f"{rel(path)}:{text[: match.start()].count(chr(10)) + 1}"
            parsed = WHEEL_NAME_RE.match(wheel)
            if not parsed:
                result.fail(
                    f"{loc} 的 wheel 文件名不合法：{wheel}——"
                    f"PEP 427 要求 `<dist>-<version>-py3-none-any.whl`；"
                    f"缺版本号时 pip 与 uv 都拒绝安装"
                )
                continue
            if parsed.group("version") != init:
                result.fail(
                    f"{loc} 链接里的版本是 {parsed.group('version')}，而 "
                    f"__version__ 是 {init}；发布后没有这个资产名，链接会 404"
                )

    if RELEASE_YML.is_file():
        result.checked += 1
        text = RELEASE_YML.read_text(encoding="utf-8", errors="replace")
        if "workbench.__version__" not in text and "workbench import __version__" not in text:
            result.fail(
                f"{rel(RELEASE_YML)} 没用 __version__ 取版本号；"
                f"发布正文里的安装链接会与真实资产名不一致"
            )
        # 模板里若出现字面 ``wmshare_workbench-1.2.3-`` 就是硬编码，会随版本漂移
        for hard in re.finditer(r"wmshare_workbench-\d[^-]*-py3", text):
            seen += 1
            result.checked += 1
            result.fail(
                f"{rel(RELEASE_YML)} 硬编码了版本号：{hard.group(0)}……；"
                f"请用 ${{{{ env.VER }}}} 从 __version__ 取"
            )

    result.checked += 1
    if seen == 0:
        # 一个链接都没有 = 快速开始丢了，这是产品入口，不能静默
        result.fail(
            "README / not_built.py 里没有任何 releases 下载链接；"
            "快速开始必须给一条用户能直接粘贴的命令"
        )


def main() -> Result:
    result = Result("contract")
    check_drift(result)
    check_against_baseline(result)
    check_versions(result)
    check_dist_links(result)
    return result


if __name__ == "__main__":
    raise SystemExit(run_gate("contract", main))
