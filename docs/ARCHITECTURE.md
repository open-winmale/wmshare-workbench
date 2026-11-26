# 架构

> 前后端同仓、双栈、单端口。本文件说明**为什么这样放**、**边界在哪**、**产物怎么到用户手里**。
> 分层规则的可执行版本在 `docs/PROJECT_SPEC.md` §2；这里的重点是结构与流程。

## 1. 整体形态

一个本地投研工作台：Python 后端取数 + Vue 前端呈现，**单进程单端口**
（`127.0.0.1:8787`）同时托管 API 与静态产物。

```
┌─────────────────────────────────────────────────────────┐
│  frontend/            Vue 3 + Vite + ECharts            │
│    features → composables → components → api/           │
│                                    ↓ 唯一 fetch 处       │
└────────────────────────────────────┬────────────────────┘
                                     │ HTTP JSON @ /api/*
                          ★ 契约边界（不得 import 跨越）
                                     │
┌────────────────────────────────────┴────────────────────┐
│  backend/workbench/   Python 3.11+，stdlib only          │
│    tools → client → platform → core                     │
└─────────────────────────────────────────────────────────┘
```

## 2. 目录布局与理由

```
wmshare-workbench/
├── Makefile              真 make（之前是 Python 脚本，`make check` 直接报错）
├── pyproject.toml        where = ["backend"]；package-data 含 static/**
├── run.py                启动入口：注入 backend/ 到 sys.path
├── gates/                质量门禁（与应用层 tools/ 物理分开）
├── backend/workbench/
│   ├── core/             depth 0：信封、单位、格式化（零 IO）
│   ├── platform/         depth 1：SQLite、凭证、HTTP、文件、日志
│   ├── client/           depth 2：hub / autoload / ec / fetchers
│   ├── tools/            depth 3：9 个工具 handler + panels
│   └── static/           前端构建产物（gitignore，但进 wheel）
├── frontend/
│   ├── src/{api,components,composables,features,styles}
│   └── vite.config.ts    outDir → ../backend/workbench/static
├── tests/                根级（含跨栈静态托管测试）
├── quality/baselines/    八份棘轮基线
└── docs/
```

### 为什么是 `backend/` + `frontend/` 而非兄弟仓的 `src/` + `web/`

`wmshare-tools` 用 `src/bigwinner/` + `web/`。本项目不跟，理由是**表达对称性**：
`src/` 暗示「Python 是本体、前端是附属」，而这里两半都重要。多数派做法也是
平级（FastAPI 官方模板、Superset 的 `superset/`+`superset-frontend/`、
Label Studio 的 `label_studio/`+`web/`）。

代价是与兄弟仓不一致，新人需要读这份文档。见 `docs/ADR/002`。

### 为什么后端不套一层 `src/`

`backend/` 本身就是源布局的隔离层：里面只有 `workbench` 一个包，从仓库根
`import workbench` 本就失败（正确行为）。再套 `src/` 是两层包装干同一件事，
且门禁报错路径多一级纯噪声。

真正的 packaging 安全靠 `gates/check_wheel.py`：构建 wheel 后**断言
`workbench/static/index.html` 在包体内**。这比「靠目录结构提醒你别犯」更强。

### 为什么 `frontend/` 里有 `src/`

这不是自由选择：Vite/tsconfig 约定 `index.html` 在项目根、代码在 `src/`。
两侧一个有 `src` 一个没有，是各自遵循本栈工具惯例。

### 为什么门禁叫 `gates/` 而不是 `tools/`

`tools/` 已经用于应用层（`backend/workbench/tools/`）。同名导致过一个真实 bug：
`check_envelope` 扫的是 `repo/tools/*/handler.py`（门禁脚本自身目录），
真实 handler 落地后完全不被检查。改名后物理可分。

## 3. 契约边界

**唯一真源**：`backend/workbench/core/envelope.py` 里的
`ENVELOPE_FIELDS` / `FRESHNESS_VALUES` / `EC_FIELDS` / `ERROR_ACTIONS` / `ENDPOINTS`。

**前端不手写这些**，读生成的 `frontend/src/api/contract.ts`：

```
make gen-contract      # backend → frontend/src/api/contract.ts
make check             # 含 check_contract：逐字节比对，手改即红
```

### 为什么不用 OpenAPI codegen

规模上（14 个端点）不需要。四个兄弟仓全是**手写双份 TS 类型、零漂移检查**——
这是被证实的坑：后端改字段名，CI 全绿，UI 里变成 `undefined`。
`winmale-v2` 为跨仓同步上了 proto submodule + 三仓提交，代价远大于收益。

我们的取法：**Python 常量 → 生成 → 逐字节漂移门禁**。与 `wmshare` 仓既有的
`tools/gen_*.py --check` 同一范式，只是产物是 TS 而不是文档。

### 端点清单也在契约里

`ENDPOINTS` 是前后端唯一的端点真源。前端不得出现手写字面量
`"/api/screener/run"`——用 `ENDPOINTS.screener.path`。新增工具必须先在
`ENDPOINTS` 登记，否则前端没有对应类型，`check_contract` 会红。

## 4. 构建与交付链路

```
frontend/src/**  ──vite build──►  backend/workbench/static/**
                                          │
                                    python -m build
                                          ▼
                                   workbench-0.1.0-py3-none-any.whl
                                   含 workbench/static/index.html
                                          │
                                    pip install
                                          ▼
                                   用户无需 Node
```

**关键决策：产物进 wheel，用户不装 Node。**

`vite.config.ts` 的 `outDir` 直接指向包内目录（照搬 `wmshare-tools`），
没有拷贝步骤、没有产物交接：

```ts
build: {
  outDir: fileURLToPath(new URL('../backend/workbench/static', import.meta.url)),
  emptyOutDir: true,
}
```

`pyproject.toml` 的 `package-data` 必须覆盖它：

```toml
[tool.setuptools.package-data]
workbench = ["py.typed", "static/**/*"]
```

**这一条是硬约束**：`wmshare-tools` 的 `web_dist/` 被 gitignore 且未列入
`package-data`，结果 `pip install` 拿到的包**既无新 UI 也无旧 UI**，只在启动时
打横幅提示（CHANGELOG 1.7.1）。`gates/check_wheel.py` 把根因堵死。

### 开发期两进程

```bash
python run.py                  # 后端 :8787
cd frontend && npm run dev     # 前端 :5173，/api 代理到 8787
```

前端热更新不需要重启后端。生产是单进程：`python run.py` 同时托管 API 与静态。

## 5. 单端口服务清单（`backend/workbench/platform/server.py` 必须逐条满足）

1. `/api/*` **前缀优先匹配**，不参与静态托管
2. `/` → `static/index.html`，`Cache-Control: no-cache`（**不是** `no-store`：
   `no-cache` = 可缓存但必须重验证，`no-store` = 禁止存储，后者会让每次刷新都
   重新下载，本地工具下无意义）
3. `/assets/*` → 文件名含 hash，`Cache-Control: public, max-age=31536000, immutable`
4. **路径穿越防御**：`(root / route).resolve()` 后断言
   `root.resolve()` 是其父路径（`realpath` + `commonpath` 比较），
   *不是*只取末段——取末段会丢掉子目录结构
5. MIME 用**显式字典**，不用 `mimetypes`（后者行为依赖操作系统注册表，
   `.js` 在某些 Windows 上会解析错）
6. `static/index.html` 不存在 → 返回 HTML 提示页（含 `make web` 指引），
   **HTTP 200 而非 500**——本地工具不该报服务器错误
7. **运行时探测**：每请求 `is_file()`，构建后刷新即生效，无需重启

### 路由用 hash（`createWebHashHistory`）

后端因此只需托管 `/` 与 `/assets/*`，**无需 SPA fallback**——这是把 stdlib
`http.server` 用到极致的前提（`wmshare-tools` 与 `sift` 同法）。

代价：URL 带 `#/`（`/#/equity/600519`）。本地工具可接受。
若要 history 路由，需加 catch-all fallback 并区分「缺资源要 404」与
「导航路径回 index.html」——见 `docs/DEBT.md` D-11。

## 6. 测试分层

| 层 | 位置 | 依赖 | 内容 |
|---|---|---|---|
| 后端单测 | `tests/test_*.py` | 无（离线） | 信封、门禁自检、hub/autoload/ec |
| 门禁自检 | `tests/test_gates_selftest.py` | 无 | 每个门禁「该红」+「该绿」两类用例 |
| 跨栈静态托管 | `tests/test_server_spa.py` | 无（伪造 dist） | MIME、API 隔离、404、提示页 |
| 前端单测 | `frontend/src/**/*.test.ts` | vitest | 格式化、数值排序键 |
| 端到端 | P6 | Playwright | 9 工具 × 2 主题 |

**跨栈测试为何伪造 dist 而不是真构建**：这样 `backend` 的 CI job 不需要 Node。
真构建产物由 `check_wheel` 在 `wheel` job 里验证（断言包内含 `static/index.html`）。

## 7. CI 结构

```yaml
jobs:
  changes:            # dorny/paths-filter：py | web
  backend:            # 离线：ruff + make check + pytest（不装 Node）
  frontend:           # Node：typecheck + build + 跑跨栈静态托管测试
  wheel:              # needs: [backend, frontend]
                      # 构建 wheel → 断言含 static/index.html → 干净 venv 冒烟
  ci-ok:              # 总是运行，needs 上面全部；唯一 required check
```

两个要点：

- **`wheel` 必须 `needs: [backend, frontend]`**。`wmshare-tools` 的两个 job 并行
  是因为它**不承诺 wheel 带 UI**；我们承诺了，所以必须有依赖。
- **`ci-ok` 聚合 job**：GitHub 的 required check 在 workflow 被路径过滤跳过时
  会永远 pending，PR 无法合并。always-run 的聚合 job 是标准解法。

## 8. 不做什么

- **不分仓**。`winmale-v2`/`winv2` 的实价：一次 API 变更三仓提交、后端生成器写
  仓外文件 231KB 且无 `--check`、CI 要 clone 第三仓、`dev.sh` 要 `go run` 后端仓
  拿 JWT。分仓在付租金且无技术理由。
- **不引入 FastAPI**。`dependencies = []`、用户 clone 即跑是核心价值；
  stdlib `ThreadingHTTPServer` 够用（`wmshare-tools` 与 `fin-extract` 同选择）。
- **不在仓库里存 `dist/`**。构建产物入库会让每次改前端产生巨大 diff，
  且容易忘记重建导致线上是旧代码。git 官方文档也把「项目构建生成的文件」
  列为 `.gitignore` 的典型用例。
- **不做旧界面回退**。`wmshare-tools` 在未构建时静默回退旧多页版，用户误以为
  拿到旧版本。我们只返回一个明确的提示页。
