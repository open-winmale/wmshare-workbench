"""AI 助手：单 agent + 按域分组的工具面（清单即契约，技能即数据）。

模块分工：

- ``registry.json`` 工具清单（通用执行器消费，防编造由契约测试守）
- ``skills.py`` + ``skills/*/SKILL.md`` 技能即数据（外置目录可扩展）
- ``executor.py`` 通用执行器（hub 取数 + 结果压缩 + 非负守卫）
- ``agent.py`` 通用工具循环（一个模型、一次装配）
- ``runner.py`` 单 agent 装配（域分组工具面 + 技能按需读 + 预算闸）
- ``ledger.py`` 来源账（宿主编号，模型只引用 [n]）
- ``llm.py`` OpenAI 兼容流式客户端（纯 stdlib）
- ``config.py`` 模型配置（env > credentials.env，DeepSeek 示例默认）
- ``jobs.py`` 任务台账（chat 异步 + stream 轮询）
- ``handler.py`` 五个端点
"""
