"""门禁自检：证明六个门禁**在注入违规时确实会失败**。

为什么必须有这个文件：一个永远返回 0 的门禁与没有门禁等价，但会给人虚假的
安全感。本文件对每个门禁做「注入违规 → 断言非零退出码 + 断言报错定位到具体
位置」的双向验证。

做法：把违规样例写进临时目录，让门禁针对临时目录跑（通过 monkeypatch 改
``_gate`` 的路径常量），而不是污染真实仓库。这样自检可以随便造违规。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GATES = REPO / "gates"
PY = sys.executable
#: 真实 ``dist/``（``check_wheel`` 的默认搜索位置）。
DIST = REPO / "dist"


def run_gate(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    """在仓库根执行门禁，返回完整结果。"""
    return subprocess.run(
        [PY, str(GATES / script), *args],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    )


def test_all_gates_pass_on_clean_repo() -> None:
    """干净仓库上已登记门禁全部通过（否则基线本身有问题）。"""
    for script, args in (
        ("check_layers.py", ()),
        ("check_sizes.py", ()),
        ("check_tokens.py", ()),
        ("check_envelope.py", ()),
        ("check_docs_links.py", ()),
        ("check_plan.py", ()),
        ("gen_component_index.py", ("--check",)),
    ):
        proc = run_gate(script, *args)
        assert proc.returncode == 0, (
            f"{script} 在干净仓库上失败：\n{proc.stdout}\n{proc.stderr}")


class TestWheelGate:
    """``check_wheel`` 的自测。

    **为什么单列**：它需要先有 wheel，不能进 ``test_all_gates_pass_on_clean_repo``
    （干净 clone 上没有 ``dist/``）。但它又必须被自测——此前它从不在任何测试里，
    于是「拿旧 wheel 判绿」这个缺陷活了很久（实测 11-25 的 wheel 引用
    ``index-4rRQcC-S.js``，而产物已是 ``index-DjAHLk_6.js``，门禁照样 OK）。
    """

    def test_fails_loudly_without_wheel(self, tmp_path: Path) -> None:
        """没有 wheel 时给可读失败，而不是崩。"""
        proc = run_gate("check_wheel.py", "--wheel", str(tmp_path / "nope.whl"))
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "找不到 wheel" in proc.stdout

    def test_fails_on_wheel_without_static(self, tmp_path: Path) -> None:
        """wheel 里没有 static/index.html → 红（这正是「装完没界面」）。"""
        wheel = tmp_path / "fake-1.0-py3-none-any.whl"
        _zip(wheel, {"fake/__init__.py": ""})
        proc = run_gate("check_wheel.py", "--wheel", str(wheel))
        assert proc.returncode == 1, proc.stdout
        assert "不含 workbench/static/index.html" in proc.stdout

    def test_fails_when_index_points_at_missing_asset(self, tmp_path: Path) -> None:
        """index.html 引用的 JS 不在包里 → 红（``build/lib`` 残留造成「拷一半」）。"""
        wheel = tmp_path / "half-1.0-py3-none-any.whl"
        _zip(wheel, {
            "workbench/static/index.html":
                '<script src="./assets/index-ABC.js"></script>',
            "workbench/static/assets/other-XYZ.js": "// 不是被引用的那个",
        })
        proc = run_gate("check_wheel.py", "--wheel", str(wheel))
        assert proc.returncode == 1, proc.stdout
        assert "包内不存在的资源" in proc.stdout

    def test_fails_on_stale_wheel(self) -> None:
        """wheel 比 static/index.html 旧 → 红（校验的是上一轮构建）。"""
        wheel = DIST / "stale-0.0.0-py3-none-any.whl"
        static_index = REPO / "backend" / "workbench" / "static" / "index.html"
        if not static_index.is_file():
            pytest.skip("本地没有前端产物，无法构造「陈旧」场景")
        _zip(wheel, {
            "workbench/static/index.html": '<script src="./assets/index-ABC.js"></script>',
            "workbench/static/assets/index-ABC.js": "// x",
        })
        old = static_index.stat().st_mtime - 3600
        os.utime(wheel, (old, old))
        try:
            proc = run_gate("check_wheel.py", "--wheel", str(wheel))
        finally:
            wheel.unlink(missing_ok=True)
        assert proc.returncode == 1, proc.stdout
        assert "校验的是上一次构建的包" in proc.stdout


def _zip(path: Path, files: dict[str, str]) -> None:
    """把一个 ``{成员名: 文本}`` 写成最小 zip（模拟 wheel）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)


# --------------------------------------------------------------------------
# 注入违规：每个用例造一个临时仓库副本，改一处，断言对应门禁转红
# --------------------------------------------------------------------------

@pytest.fixture()
def sandbox(tmp_path: Path) -> Path:
    """复制最小骨架到临时目录（gates + backend + docs + quality + tests + Makefile）。

    ``tests/`` 与 ``Makefile`` 必须一起复制：``check_plan`` 会用它们校验台账
    里的 ``evidence`` 是否指向真实存在的对象。缺了它们，自检会因为「证据不存在」
    而红，掩盖掉我们真正想验的违规。
    """
    import shutil

    for name in ("gates", "backend", "docs", "quality", "tests", "frontend"):
        src = REPO / name
        if not src.is_dir():
            (tmp_path / name).mkdir(parents=True)
            continue
        shutil.copytree(src, tmp_path / name,
                        ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    for f in ("Makefile", "pyproject.toml"):
        if (REPO / f).is_file():
            shutil.copy2(REPO / f, tmp_path / f)
    return tmp_path


def run_in(root: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(root / "gates" / script), *args],
        cwd=root, capture_output=True, text=True, timeout=60,
    )


def test_layers_detects_violation(sandbox: Path) -> None:
    """core 层 import 上层 → 反向依赖，必须红。"""
    target = sandbox / "backend" / "workbench" / "core" / "leak.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from workbench.client import hub\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_layers.py")
    assert proc.returncode == 1, proc.stdout
    assert "core 是叶子层" in proc.stdout or "反向依赖" in proc.stdout
    assert "leak.py" in proc.stdout


def test_sizes_detects_violation(sandbox: Path) -> None:
    """文件行数超过基线 → 棘轮不得放大，必须红。"""
    target = sandbox / "backend" / "workbench" / "core" / "envelope.py"
    original = target.read_text(encoding="utf-8")
    target.write_text(original + "\n# pad\n" * 30, encoding="utf-8")
    proc = run_in(sandbox, "check_sizes.py")
    assert proc.returncode == 1, proc.stdout
    assert "超过基线" in proc.stdout
    assert "envelope.py" in proc.stdout


def test_tokens_detects_violation(sandbox: Path) -> None:
    """组件里写裸 hex → 必须红。"""
    comp = sandbox / "frontend" / "src" / "components" / "ui"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "Bad.vue").write_text(
        "<template><div class=\"x\">hi</div></template>\n"
        "<style scoped>.x { color: #ff0000; }</style>\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_tokens.py")
    assert proc.returncode == 1, proc.stdout
    assert "裸色值" in proc.stdout
    assert "Bad.vue" in proc.stdout


def test_tokens_ignores_vue_slot_shorthand(sandbox: Path) -> None:
    """``<template #fee>`` 是槽位名，不是颜色——不能判成裸色值。

    这条是误报的回归测试：``#fee`` 三个字符全是 hex 字母，会被三位色值
    正则命中。误报的代价是规则被绕过（开发者会去改槽位名而不是改颜色），
    所以必须精确排除。
    """
    comp = sandbox / "frontend" / "src" / "components" / "ui"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "Slots.vue").write_text(
        "<template>\n"
        "  <DataTable>\n"
        "    <template #fee=\"{ row }\">{{ row.fee }}</template>\n"
        "    <template #abc>{{ 1 }}</template>\n"
        "  </DataTable>\n"
        "</template>\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_tokens.py")
    assert "裸色值" not in proc.stdout, proc.stdout


def test_tokens_still_catches_hex_next_to_slot(sandbox: Path) -> None:
    """槽位豁免不能放宽到整行——同一行里的真色值仍要红。"""
    comp = sandbox / "frontend" / "src" / "components" / "ui"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "Mixed.vue").write_text(
        "<template><div class=\"x\" /></template>\n"
        "<style scoped>\n"
        "/* <template #fee> 是槽位，但下一行是真颜色 */\n"
        ".x { color: #c0ffee; }\n"
        "</style>\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_tokens.py")
    assert proc.returncode == 1, proc.stdout
    assert "裸色值" in proc.stdout


def test_tokens_detects_missing_token(sandbox: Path) -> None:
    """tokens.css 缺必需令牌 → 必须红。"""
    styles = sandbox / "frontend" / "src" / "styles"
    styles.mkdir(parents=True, exist_ok=True)
    (styles / "tokens.css").write_text(":root { --wb-bg-base: #000; }\n",
                                       encoding="utf-8")
    proc = run_in(sandbox, "check_tokens.py")
    assert proc.returncode == 1, proc.stdout
    assert "缺少令牌" in proc.stdout


def test_envelope_detects_violation(sandbox: Path) -> None:
    """ok=False 却带非空 data → 必须红。"""
    handler_dir = sandbox / "backend" / "workbench" / "tools" / "demo"
    handler_dir.mkdir(parents=True, exist_ok=True)
    (handler_dir / "handler.py").write_text(
        "from __future__ import annotations\n"
        "from workbench.core.envelope import build\n\n\n"
        "def run():\n"
        "    return build(ok=False, data={'oops': 1})\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_envelope.py")
    assert proc.returncode == 1, proc.stdout
    assert "data 非空" in proc.stdout


def test_envelope_detects_unknown_field(sandbox: Path) -> None:
    """信封出现契约外字段 → 必须红。"""
    handler_dir = sandbox / "backend" / "workbench" / "tools" / "demo"
    handler_dir.mkdir(parents=True, exist_ok=True)
    (handler_dir / "handler.py").write_text(
        "from __future__ import annotations\n\n\n"
        "def run():\n"
        "    return {'ok': True, 'data': {}, 'retry_hint': 'x'}\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_envelope.py")
    assert proc.returncode == 1, proc.stdout
    assert "契约外字段" in proc.stdout


def test_envelope_detects_ec_zero(sandbox: Path) -> None:
    """无成本模型却写 pred_lo=0 → 必须红（0 会被读成免费）。"""
    handler_dir = sandbox / "backend" / "workbench" / "tools" / "demo"
    handler_dir.mkdir(parents=True, exist_ok=True)
    (handler_dir / "handler.py").write_text(
        "from __future__ import annotations\n\n\n"
        "def run():\n"
        "    return {'ok': True, 'data': {}, 'ec': {'pred_lo': 0, 'pred_hi': 0}}\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_envelope.py")
    assert proc.returncode == 1, proc.stdout
    assert "pred_lo" in proc.stdout


def test_envelope_contract_matches_baseline(sandbox: Path) -> None:
    """代码与基线的字段集必须一致（改基线不改代码 → 红）。"""
    baseline = sandbox / "quality" / "baselines" / "envelope.json"
    data = json.loads(baseline.read_text(encoding="utf-8"))
    data["fields"].append("surprise")
    baseline.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    proc = run_in(sandbox, "check_envelope.py")
    assert proc.returncode == 1, proc.stdout
    assert "信封字段不一致" in proc.stdout


def test_plan_detects_violation(sandbox: Path) -> None:
    """done 缺 evidence → 必须红。"""
    progress = sandbox / "docs" / "PROGRESS.md"
    text = progress.read_text(encoding="utf-8")
    text = text.replace(
        "| P0-01 | docs | docs | done | 三份规范文件存在且各含「可机械验证」条款标注 "
        "| `docs/PROJECT_SPEC.md` · `docs/TRACKING.md` · `docs/DESIGN_SYSTEM.md` "
        "| none | 2026-11-25 |",
        "| P0-01 | docs | docs | done | 三份规范文件存在且各含「可机械验证」条款标注 "
        "| — | none | 2026-11-25 |", 1)
    progress.write_text(text, encoding="utf-8")
    proc = run_in(sandbox, "check_plan.py")
    assert proc.returncode == 1, proc.stdout
    assert "evidence 为空" in proc.stdout


def test_plan_detects_bad_stats(sandbox: Path) -> None:
    """统计行与表格不符 → 必须红（禁止手改数字）。"""
    progress = sandbox / "docs" / "PROGRESS.md"
    text = progress.read_text(encoding="utf-8")
    m = re.search(r"\*\*统计\*\*：总计 (\d+)", text)
    assert m, "PROGRESS.md 缺少统计行"
    text = text.replace(f"**统计**：总计 {m.group(1)}",
                        f"**统计**：总计 {int(m.group(1)) + 1}", 1)
    progress.write_text(text, encoding="utf-8")
    proc = run_in(sandbox, "check_plan.py")
    assert proc.returncode == 1, proc.stdout
    assert "统计行与表格不符" in proc.stdout


def test_plan_detects_bare_todo(sandbox: Path) -> None:
    """裸 TODO（无工作项 id）→ 必须红。"""
    (sandbox / "backend" / "workbench" / "core" / "bad.py").write_text(
        "from __future__ import annotations\n\n"
        "# TODO: 以后补上缓存\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_plan.py")
    assert proc.returncode == 1, proc.stdout
    assert "未带工作项 id" in proc.stdout


def test_plan_ignores_todo_in_code_span(sandbox: Path) -> None:
    """规范说明中的反引号 TODO 不算违规（否则规则会自我违反）。"""
    (sandbox / "backend" / "workbench" / "core" / "doc.py").write_text(
        "from __future__ import annotations\n\n"
        '"""规则：任何 `TODO` 必须形如 `TODO(P3-07): x`。"""\n',
        encoding="utf-8")
    proc = run_in(sandbox, "check_plan.py")
    assert proc.returncode == 0, proc.stdout


def test_plan_detects_bad_debt_row(sandbox: Path) -> None:
    """债务缺 trigger → 必须红。"""
    debt = sandbox / "docs" / "DEBT.md"
    text = debt.read_text(encoding="utf-8")
    text = text.replace("| 两仓 `portfolio` 计算函数出现第 2 处不一致 |",
                        "|  |", 1)
    debt.write_text(text, encoding="utf-8")
    proc = run_in(sandbox, "check_plan.py")
    assert proc.returncode == 1, proc.stdout
    assert "缺少 trigger" in proc.stdout


def test_components_detects_orphan(sandbox: Path) -> None:
    """孤儿组件（0 引用）→ 必须红。"""
    comp = sandbox / "frontend" / "src" / "components" / "ui"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "Lonely.vue").write_text(
        "<template><div>nobody uses me</div></template>\n", encoding="utf-8")
    write = run_in(sandbox, "gen_component_index.py", "--write")
    assert write.returncode == 0, write.stdout
    proc = run_in(sandbox, "gen_component_index.py", "--check")
    assert proc.returncode == 1, proc.stdout
    assert "孤儿组件" in proc.stdout


def test_gate_error_exit_code(tmp_path: Path) -> None:
    """基线缺失 → 门禁自身故障，退出码 2（区别于违规的 1）。"""
    import shutil

    for name in ("gates", "backend", "docs"):
        shutil.copytree(REPO / name, tmp_path / name,
                        ignore=shutil.ignore_patterns("__pycache__"))
    proc = run_in(tmp_path, "check_sizes.py")
    assert proc.returncode == 2, proc.stdout
    assert "基线缺失" in proc.stderr


# ==========================================================================
# 架构修复的验证（2026-11-25 重构）：每条对应一个曾经失效的门禁
# ==========================================================================

def test_layers_allows_whitelisted_downward_edge(sandbox: Path) -> None:
    """白名单边必须**绿**。

    旧版 check_layers 的 `order[dst] < order[src]` 判定把每条合法向下边都
    当成反向依赖——这条用例就是当时缺失的那一半：只测「会红」不测「该绿」，
    于是反转的 bug 一直没被发现（仓库里零跨层 import 让门禁永远扫 0 项）。
    """
    probe = sandbox / "backend" / "workbench" / "client" / "probe.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(
        "from __future__ import annotations\n"
        "from workbench.core import envelope\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_layers.py")
    assert proc.returncode == 0, proc.stdout


def test_layers_detects_relative_import(sandbox: Path) -> None:
    """相对 import 绕过分层 = 最危险的漏检（旧版 `if node.level: continue`）。"""
    leak = sandbox / "backend" / "workbench" / "core" / "rel.py"
    leak.write_text(
        "from __future__ import annotations\n"
        "from ..client import hub\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_layers.py")
    assert proc.returncode == 1, proc.stdout
    assert "rel.py" in proc.stdout


def test_layers_detects_platform_importing_tools(sandbox: Path) -> None:
    """``platform/`` 里 import ``tools`` 必须红（HTTP 机制不该依赖业务）。

    上一版这条测的是「深度 1 的 server.py 免检」；引入 ``bootstrap`` 组合根后
    深度 1 归 bootstrap 且**允许** import tools（装配者的正当职责），
    所以改成测真正违规的方向。
    """
    entry = sandbox / "backend" / "workbench" / "platform" / "probe.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "from __future__ import annotations\n"
        "from workbench.tools import demo\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_layers.py")
    assert proc.returncode == 1, proc.stdout
    assert "反向依赖" in proc.stdout or "未登记" in proc.stdout


def test_layers_allows_bootstrap_imports_tools(sandbox: Path) -> None:
    """组合根 import tools 必须**绿**——它是唯一允许装配全部层的地方。

    与上一条配对：只测「会红」会让门禁退化成「永远红」而被关掉；
    只测「该绿」会让它退化成「永远绿」而无人察觉。
    """
    entry = sandbox / "backend" / "workbench" / "bootstrap.py"
    entry.write_text(
        "from __future__ import annotations\n"
        "from workbench.tools.appinfo import handler\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_layers.py")
    assert proc.returncode == 0, proc.stdout


def test_layers_detects_tool_cross_import(sandbox: Path) -> None:
    """工具之间横向 import（旧版别名映射后仍按字面量匹配，抓不到）。"""
    for name in ("a", "b"):
        d = sandbox / "backend" / "workbench" / "tools" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("", encoding="utf-8")
    (sandbox / "backend" / "workbench" / "tools" / "a" / "handler.py").write_text(
        "from __future__ import annotations\n"
        "from workbench.tools.b import handler\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_layers.py")
    assert proc.returncode == 1, proc.stdout
    assert "工具横向依赖" in proc.stdout


def test_layers_detects_frontend_fetch_outside_api(sandbox: Path) -> None:
    """前端 fetch 只许在 api/ 层。"""
    comp = sandbox / "frontend" / "src" / "components"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "Bad.vue").write_text(
        "<script setup lang=\"ts\">\nfetch('/api/x');\n</script>\n",
        encoding="utf-8")
    proc = run_in(sandbox, "check_layers.py")
    assert proc.returncode == 1, proc.stdout
    assert "fetch 只能在 api/" in proc.stdout


def test_sizes_detects_slack_in_baseline(sandbox: Path) -> None:
    """基线远高于实际 → 告警（隐性松弛也是缺陷）。"""
    baseline = sandbox / "quality" / "baselines" / "sizes.json"
    data = json.loads(baseline.read_text(encoding="utf-8"))
    key = "backend/workbench/core/envelope.py"
    data["baseline"][key] = data["baseline"][key] + 100
    baseline.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    proc = run_in(sandbox, "check_sizes.py")
    assert "高出" in proc.stdout, proc.stdout


def test_sizes_detects_tool_handler_cap(sandbox: Path) -> None:
    """handler.py 有单独上限（旧版从未读取该配置）。"""
    handler = sandbox / "backend" / "workbench" / "tools" / "demo" / "handler.py"
    handler.parent.mkdir(parents=True, exist_ok=True)
    handler.write_text("from __future__ import annotations\n" + "\n# pad\n" * 320,
                       encoding="utf-8")
    proc = run_in(sandbox, "check_sizes.py")
    assert proc.returncode == 1, proc.stdout
    assert "超过上限" in proc.stdout


def test_tokens_requires_both_themes(sandbox: Path) -> None:
    """只写 :root 不写 daylight → 红（旧版只在全文找一次）。"""
    styles = sandbox / "frontend" / "src" / "styles"
    styles.mkdir(parents=True, exist_ok=True)
    baseline = json.loads(
        (sandbox / "quality" / "baselines" / "tokens.json").read_text(encoding="utf-8"))
    required = baseline["required_in_both_themes"]
    root = "\n".join(f"  --wb-{n}: #000;" for n in required)
    (styles / "tokens.css").write_text(":root {\n" + root + "\n}\n", encoding="utf-8")
    proc = run_in(sandbox, "check_tokens.py")
    assert proc.returncode == 1, proc.stdout
    assert "daylight" in proc.stdout


def test_plan_detects_duplicate_id(sandbox: Path) -> None:
    """台账 ID 重复 → 红（旧版不查，P1-01 曾出现两次）。"""
    progress = sandbox / "docs" / "PROGRESS.md"
    text = progress.read_text(encoding="utf-8")
    dup = ("| P0-01 | docs | docs | proposed | 重复项 | — | none | 2026-11-25 |\n")
    text = text.replace("## P0 · 规范与骨架\n\n",
                        "## P0 · 规范与骨架\n\n" + dup, 1)
    progress.write_text(text, encoding="utf-8")
    proc = run_in(sandbox, "check_plan.py")
    assert proc.returncode == 1, proc.stdout
    assert "ID 重复" in proc.stdout


def test_plan_detects_stage_done_with_pending(sandbox: Path) -> None:
    """阶段标 done 但仍有未完成工作项 → 红（TRACKING §5 规则 2，旧版未实现）。

    动态挑一个「台账里确实还有未完成项」的阶段，避免台账推进后本用例失效。
    """
    plan = sandbox / "docs" / "PLAN.md"
    progress = sandbox / "docs" / "PROGRESS.md"

    rows = re.findall(r"^\| (P\d+)-\d+ \|[^|]*\|", progress.read_text(encoding="utf-8"),
                      re.M)
    pending_ids = re.findall(
        r"^\| (P\d+)-\d+ \|[^|]*\|[^|]*\| (proposed|accepted|in_progress) \|",
        progress.read_text(encoding="utf-8"), re.M)
    stages_with_pending = {s for s, _ in pending_ids}
    assert stages_with_pending, "台账里应当还有未完成项（否则本用例无从验证）"
    assert rows, "台账解析失败"

    stage = sorted(stages_with_pending)[0]
    text = plan.read_text(encoding="utf-8")
    new_text, n = re.subn(rf"(\| {stage} \|[^|]*\|[^|]*\| )`\w+`( \|)",
                          r"\1`done`\2", text, count=1)
    assert n == 1, f"PLAN.md 未找到 {stage} 阶段行"
    plan.write_text(new_text, encoding="utf-8")

    proc = run_in(sandbox, "check_plan.py")
    assert proc.returncode == 1, proc.stdout
    assert "未完成项" in proc.stdout

def test_contract_detects_drift(sandbox: Path) -> None:
    """手改 contract.ts → 红（生成物不手改的物理保证）。"""
    contract = sandbox / "frontend" / "src" / "api" / "contract.ts"
    if not contract.is_file():
        pytest.skip("sandbox 未含 contract.ts")
    text = contract.read_text(encoding="utf-8")
    contract.write_text(text.replace("ENVELOPE_VERSION = 1", "ENVELOPE_VERSION = 99", 1),
                        encoding="utf-8")
    proc = run_in(sandbox, "check_contract.py")
    assert proc.returncode == 1, proc.stdout
    assert "契约漂移" in proc.stdout


def test_contract_detects_version_drift(sandbox: Path) -> None:
    """三处版本号不一致 → 红（wmshare-tools CHANGELOG 1.7.1 踩过）。"""
    pkg = sandbox / "frontend" / "package.json"
    if not pkg.is_file():
        pytest.skip("sandbox 未含 package.json")
    data = json.loads(pkg.read_text(encoding="utf-8"))
    data["version"] = "9.9.9"
    pkg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    proc = run_in(sandbox, "check_contract.py")
    assert proc.returncode == 1, proc.stdout
    assert "版本不一致" in proc.stdout


def test_makefile_is_real_make() -> None:
    """`Makefile` 必须能被 make 解析（旧版是 Python 脚本，`make check` 直接报错）。"""
    proc = subprocess.run(["make", "-n", "check"], cwd=REPO,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert "check_layers.py" in proc.stdout


def test_run_py_exists_and_importable() -> None:
    """`run.py` 必须存在（旧版 Makefile run 与 PLAN 都引用它但文件缺失）。"""
    run_py = REPO / "run.py"
    assert run_py.is_file()
    proc = subprocess.run([PY, str(run_py), "--version"], cwd=REPO,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert "workbench" in proc.stdout


def test_test_baseline_counts_class_methods(sandbox: Path) -> None:
    """类内 `def test_` 必须计入下限棘轮。

    旧版正则写 `^def test_`，只匹配模块级函数；而 pytest 的主流写法是
    `class TestXxx:` + 缩进方法。两者叠加的结果是**新写的测试一个都不计入**，
    下限棘轮因此永远绿——这正是 `PROJECT_SPEC` §12 记录的
    「声称校验但未实现」的第 N 个实例。
    """
    tests_dir = sandbox / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    # 只写类内方法（模块级一个都没有），并把下限设成 3
    (tests_dir / "test_hub_cases.py").write_text(
        "class TestHub:\n"
        "    def test_a(self):\n        assert True\n\n"
        "    def test_b(self):\n        assert True\n\n"
        "    def test_c(self):\n        assert True\n",
        encoding="utf-8")
    baseline = sandbox / "quality" / "baselines" / "tests.json"
    data = json.loads(baseline.read_text(encoding="utf-8"))
    # 下限取一个真实测试数能超过的值（sandbox 会复制真实 tests/）
    data["per_tool"] = {"hub": 1}
    baseline.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    proc = run_in(sandbox, "check_plan.py")
    assert "scope hub 的测试数" not in proc.stdout, proc.stdout


def test_test_baseline_detects_shortfall(sandbox: Path) -> None:
    """低于下限必须红（该红用例，配对上面那条）。"""
    tests_dir = sandbox / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_hub_cases.py").write_text(
        "class TestHub:\n    def test_a(self):\n        assert True\n",
        encoding="utf-8")
    baseline = sandbox / "quality" / "baselines" / "tests.json"
    data = json.loads(baseline.read_text(encoding="utf-8"))
    # 下限高到不可能满足 → 必须红
    data["per_tool"] = {"hub": 100000}
    baseline.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    proc = run_in(sandbox, "check_plan.py")
    assert proc.returncode == 1, proc.stdout
    assert "低于下限" in proc.stdout
