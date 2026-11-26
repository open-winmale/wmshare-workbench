# wmshare-workbench 任务入口
#
# 全部目标离线、零网络、零凭证（`web`/`wheel` 例外，需 Node 或构建工具）。
# 门禁脚本在 gates/，应用代码在 backend/，前端在 frontend/。

PY ?= python3
PYTHON_DIRS := backend gates tests

.PHONY: help fmt lint check test preview web wheel gen-contract run smoke clean

help:  ## 列出所有目标
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

fmt:  ## 格式化（ruff format + 自动修复）
	$(PY) -m ruff format $(PYTHON_DIRS)
	$(PY) -m ruff check --fix $(PYTHON_DIRS)

lint:  ## 静态检查（只报不改）
	$(PY) -m ruff format --check $(PYTHON_DIRS)
	$(PY) -m ruff check $(PYTHON_DIRS)

check:  ## 全部质量门禁（离线，<30s）
	$(PY) gates/check_layers.py
	$(PY) gates/check_sizes.py
	$(PY) gates/check_tokens.py
	$(PY) gates/check_envelope.py
	$(PY) gates/check_contract.py
	$(PY) gates/check_docs_links.py
	$(PY) gates/check_plan.py
	$(PY) gates/gen_component_index.py --check

test:  ## 离线测试
	$(PY) -m pytest -q

preview: check test  ## 门禁 + 测试（提交前一把过）

smoke:  ## 真实模式冒烟：逐工具发真实请求（需服务已启动+自有凭证；CI 不跑）
	$(PY) gates/smoke.py --port 8799

gen-contract:  ## 从 Python 契约生成 frontend/src/api/contract.ts
	$(PY) gates/gen_contract.py

web:  ## 构建前端产物到 backend/workbench/static/（需 Node ≥ 18.18）
	cd frontend && npm ci && npm run build

wheel:  ## 构建 wheel 并断言内含前端产物
	$(PY) -m build --wheel
	$(PY) gates/check_wheel.py

run:  ## 启动工作台（装了 wmshare 即免注册真实数据；未装给接入指引）
	$(PY) run.py

clean:  ## 清理构建与缓存
	rm -rf dist build .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf backend/workbench/static
