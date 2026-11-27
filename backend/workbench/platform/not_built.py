"""未构建前端时的提示页（纯静态 HTML，无依赖）。

**为什么单独一个模块**：``platform/server.py`` 有 350 行棘轮，而这段 HTML
是「用户撞墙后唯一的补救指引」，值得独立成文件并写清它的坑。

**面向最终用户，不是开发者**：多数人只需要「装自带界面的预构建包」这条路，
从源码构建是第二条。所以第一条给 pip 命令，第二条才说 Node。

**坑一（2026-11-26 实测）**：这段字符串**不是** f-string。如果 CSS 里按
f-string 习惯写成 ``body{{...}}``，大括号会原样输出，整段样式失效——页面
白底无样式，``<pre>`` 里的 ``#`` 还会被浏览器当标题渲染。而这是用户看到
的唯一指引，坏了等于没有。``tests/test_platform.py`` 有一条断言钉住
「HTML 里不得出现 ``{{``」。

**坑二（同一天）**：下载地址一度写成不带版本号的
``wmshare_workbench-py3-none-any.whl``，看着「链接永久有效」，实际 **pip 与 uv
都拒绝安装**——PEP 427 规定 wheel 文件名必须是 ``name-version-py3-none-any.whl``，
``latest`` 这类词不是合法版本号（uv 原话：「expected version to start with a
number」）。于是「快速开始」第一行就是死的，而当时所有门禁与测试全绿：
没人把那条命令真的跑一遍。现在文件名由 ``__version__`` 拼出，
``gates/check_contract.py`` 断言全仓的分发链接都指向它。
"""

from __future__ import annotations

from workbench import __version__

__all__ = ["NOT_BUILT_HTML", "WHEEL_NAME", "WHEEL_URL"]

#: 分发包的文件名。**必须带版本号**（PEP 427），否则 pip/uv 拒绝安装。
WHEEL_NAME = f"wmshare_workbench-{__version__}-py3-none-any.whl"

#: 预构建包的下载地址：``/releases/latest/download/`` + 上面的文件名。
#: 链接里带版本号不影响稳定性——``latest`` 指向最新 release，而资产名随
#: 版本更新；README 与这里的版本号由门禁钉住，不会漂移。
WHEEL_URL = (
    "https://github.com/open-winmale/wmshare-workbench/releases/latest/download/" + WHEEL_NAME
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
