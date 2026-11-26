"""未构建前端时的提示页（纯静态 HTML，无依赖）。

**为什么单独一个模块**：``platform/server.py`` 有 350 行棘轮，而这段 HTML
是「用户撞墙后唯一的补救指引」，值得独立成文件并写清它的坑。

**面向最终用户，不是开发者**：多数人只需要「装自带界面的预构建包」这条路，
从源码构建是第二条。所以第一条给 pip 命令，第二条才说 Node。

**坑（2026-11-26 实测）**：这段字符串**不是** f-string。如果 CSS 里按
f-string 习惯写成 ``body{{...}}``，大括号会原样输出，整段样式失效——页面
白底无样式，``<pre>`` 里的 ``#`` 还会被浏览器当标题渲染。而这是用户看到
的唯一指引，坏了等于没有。``tests/test_platform.py`` 有一条断言钉住
「HTML 里不得出现 ``{{``」。
"""

from __future__ import annotations

__all__ = ["NOT_BUILT_HTML"]

#: 预构建包的固定下载地址（release workflow 每次都传同名副本，故不随版本变）。
WHEEL_URL = (
    "https://github.com/open-winmale/wmshare-workbench/releases/latest/download/"
    "wmshare_workbench-py3-none-any.whl"
)

NOT_BUILT_HTML = (
    """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>wmshare-workbench · 前端未构建</title>
<style>
 :root { color-scheme: light dark; }
 body { font: 15px/1.7 -apple-system, "Segoe UI", "Noto Sans SC", sans-serif;
        max-width: 44em; margin: 10vh auto; padding: 0 24px; }
 h1 { font-size: 1.4em; margin-bottom: .4em; }
 <code, pre { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; }
 code { background: rgba(127,127,127,.14); border-radius: 4px; padding: 2px 6px; }
 pre { background: rgba(127,127,127,.10); border: 1px solid rgba(127,127,127,.25);
       border-radius: 8px; padding: 14px 16px; overflow-x: auto;
       white-space: pre-wrap; word-break: break-all; }
 .hint { opacity: .72; font-size: .92em; }
 a { color: #2f6feb; }
 @media (prefers-color-scheme: dark) { a { color: #6ea8fe; } }
</style></head><body>
<h1>前端尚未构建</h1>
<p>后端已在运行（API 可用），但程序包里没有前端产物
<code>workbench/static/index.html</code>。</p>

<p><strong>如果你只是想用这个工具</strong>：换用自带界面的预构建包，无需 Node，
也不用克隆仓库：</p>
<pre>pip install WHEEL_URL_PLACEHOLDER</pre>

<p><strong>如果你是从源码运行的</strong>：构建一次即可（需要 Node ≥ 18.18）：</p>
<pre>python -m workbench.build</pre>

<p class="hint">构建完成后刷新本页即可，无需重启服务。</p>
<p class="hint">API 仍可使用：<a href="/api/health">/api/health</a> ·
<a href="/api/appinfo">/api/appinfo</a> · <a href="/api/tools">/api/tools</a></p>
</body></html>
"""
).replace("WHEEL_URL_PLACEHOLDER", WHEEL_URL)
