"""前后端工具清单一致性：`api/tools.ts` 必须与后端契约逐项对齐。

**为什么需要这条**：前端路由表 `frontend/src/api/tools.ts` 是**构建期**的
（路由必须在打包时就存在，不能运行时才决定有哪些页面）。它与后端
`core/envelope.ENDPOINTS` 是两份独立维护的清单——没有任何机制时必然漂移，
表现形式是「后端加了工具，前端导航里没有」或「前端有个页面，点了 404」。

`contract.ts` 的漂移由 `gates/check_contract.py` 逐字节比对；但那个文件是
**生成物**，不含「哪些工具该出现在导航里」这层信息。所以这一层必须单独校验。

**为什么放在 Python 而不是前端测试**：项目的测试体系是 pytest（零前端
测试框架依赖）。从 Python 侧读 `tools.ts` 的文本比引入 vitest 便宜得多，
且能直接对比 `ENDPOINTS` 这个唯一真源。
"""

from __future__ import annotations

import re
from pathlib import Path

from workbench.core.envelope import ENDPOINTS

REPO = Path(__file__).resolve().parent.parent
TOOLS_TS = REPO / "frontend" / "src" / "api" / "tools.ts"

#: 系统端点 —— 不是「工具页」，不进导航。
#: ``appinfo`` / ``tools`` / ``health`` 由页顶与状态条内部消费；
#: ``key`` 是凭证写入接口（设置流程用），不做成独立页面；
#: ``assistant_*`` 是助手页内部消费的辅助端点（info/chat/stream/stop/会话），
#: 页面入口只有 ``assistant`` 一个 slug。
SYSTEM_SLUGS = frozenset({"appinfo", "tools", "health", "key",
                          "assistant_chat", "assistant_stream",
                          "assistant_stop", "assistant_sessions",
                          "assistant_session"})


def _ui_slugs() -> set[str]:
    text = TOOLS_TS.read_text(encoding="utf-8")
    return set(re.findall(r"slug:\s*'(\w+)'", text))


def test_tools_ts_exists() -> None:
    """路由表必须存在（缺失时下面的断言会给出误导性结果）。"""
    assert TOOLS_TS.is_file(), f"缺少 {TOOLS_TS}"


def test_every_endpoint_has_a_page() -> None:
    """后端每个工具端点都要有对应的前端页面。

    缺页的后果：后端能力已经就绪、API 可用，但用户在任何界面里都点不到它。
    """
    expected = set(ENDPOINTS) - SYSTEM_SLUGS
    missing = expected - _ui_slugs()
    assert not missing, f"后端有端点但前端无页面：{sorted(missing)}"


def test_no_orphan_pages() -> None:
    """前端不能有后端不存在的页面（点了会 404）。

    这类问题比缺页更糟：用户点进去看到的是错误页，而它长得像个功能。
    """
    extra = _ui_slugs() - set(ENDPOINTS)
    assert not extra, f"前端有页面但后端无端点：{sorted(extra)}"


def test_system_slugs_are_not_pages() -> None:
    """系统端点不应被做成工具页（它们没有独立的「一页」语义）。"""
    leaked = _ui_slugs() & SYSTEM_SLUGS
    assert not leaked, f"这些系统端点被错误地加成工具页：{sorted(leaked)}"


def test_default_slug_is_a_real_page() -> None:
    """默认首页必须是一个真实页面（否则首屏白屏）。"""
    text = TOOLS_TS.read_text(encoding="utf-8")
    match = re.search(r"DEFAULT_SLUG:\s*ToolSlug\s*=\s*'(\w+)'", text)
    assert match, "tools.ts 未声明 DEFAULT_SLUG"
    assert match.group(1) in _ui_slugs(), \
        f"DEFAULT_SLUG={match.group(1)!r} 不在工具清单里"


def test_every_page_is_routed_in_app() -> None:
    """`App.vue` 的 VIEWS 表必须覆盖全部工具 slug。

    漏一个的后果：导航按钮能点，但内容区渲染的是兜底页（驾驶舱）——
    用户会以为自己点错了，或者以为那个工具就是这个样子。
    """
    app = (REPO / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    routed = set(re.findall(r"^\s{2}(\w+):\s*\w+View,", app, re.M))
    missing = _ui_slugs() - routed
    assert not missing, f"App.vue 的 VIEWS 缺这些 slug：{sorted(missing)}"


def test_reduced_motion_is_honored() -> None:
    """`tokens.css` 必须声明 `prefers-reduced-motion` 覆盖。

    设计系统把它列为「已实现」，但原来没有任何机械校验——
    删掉那段媒体查询不会有任何东西变红，「已实现」就成了自我声明。
    """
    css = (REPO / "frontend" / "src" / "styles" / "tokens.css").read_text(
        encoding="utf-8")
    assert "prefers-reduced-motion" in css, "tokens.css 缺 prefers-reduced-motion"
    assert "animation-duration" in css and "transition-duration" in css, \
        "reduced-motion 块必须同时关掉 animation 与 transition"


def test_cvd_variant_exists() -> None:
    """色觉障碍变体（`[data-cvd]`）必须存在（覆盖矩阵 §6.3 声明为「完整」）。"""
    css = (REPO / "frontend" / "src" / "styles" / "tokens.css").read_text(
        encoding="utf-8")
    assert "[data-cvd" in css, "tokens.css 缺色觉障碍变体"


def test_chart_palette_has_twelve_and_is_ordered() -> None:
    """12 色图表调色板顺序不可变（色盲相邻对已校验过）。

    顺序被重排时相邻系列会在色盲视角下撞色，而肉眼看不出来。
    """
    css = (REPO / "frontend" / "src" / "styles" / "tokens.css").read_text(
        encoding="utf-8")
    found = re.findall(r"--wb-chart-(\d+):\s*(#[0-9a-fA-F]{6})", css)
    light = {}
    for idx, hexv in found:
        light.setdefault(int(idx), hexv)
    assert sorted(light) == list(range(1, 13)), f"调色板不足 12 色：{sorted(light)}"
    # 与 ADR-001 记录的移植顺序逐值比对
    expected = ["#f5ae39", "#3fb1ea", "#9c51cc", "#ffb8df", "#4680f1", "#b98749",
                "#b7c9fc", "#e45cbe", "#5ed9e6", "#f67f2f", "#b7a1f5", "#f0d947"]
    actual = [light[i] for i in range(1, 13)]
    assert actual == expected, f"调色板顺序被改动：{actual}"


def test_default_theme_is_light_and_persisted() -> None:
    """商务主题 P0：首屏默认亮色，主题/CVD 选择经 prefs 持久化。

    没有这条时「默认亮色」只是 CSS 注释：index.html 少一个属性、App 少
    一次 savePref，刷新就回到暗色，而所有其它测试仍然全绿。
    """
    html = (REPO / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'data-theme="daylight"' in html, "index.html 缺默认亮色（会先闪暗色）"

    app = (REPO / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    assert "loadPref" in app and "savePref" in app, "App 未接 prefs 持久化"
    assert "savePref('theme'" in app, "主题切换未保存"
    assert "savePref('cvd'" in app, "CVD 切换未保存"

    state = (REPO / "frontend" / "src" / "styles" / "themeState.ts").read_text(
        encoding="utf-8")
    assert "('daylight')" in state, "themeState 默认值不是亮色"
