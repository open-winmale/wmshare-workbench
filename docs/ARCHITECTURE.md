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
frontend/src/**  ──vite build──►  backend/workbench/static/**   （不入库）
                                          │
                            python -m workbench.build
                                          ▼
                                   python -m build --wheel
                                          ▼
                        wmshare_workbench-0.1.0-py3-none-any.whl
                          含 workbench/static/index.html
                                          │
                              ├── GitHub Release（release.yml）→ pip install <url>
                              └── pip install（源码路径，需先构建）
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

### 两个构建期的坑（都踩过，都有守卫）

1. **产物是 gitignore 的，所以干净 clone 里根本没有 `static/`**。`package-data`
   的 glob 匹配零个文件时 setuptools **静默通过**——打出的 wheel 没有界面。
   构建入口 `python -m workbench.build` 在构建后自检产物完整性；`check_wheel`
   再断言 wheel 内确实有 `index.html` 且它引用的 assets 都在包里。
2. **`python -m build` 的 `build/lib` 只增不删**（`copy_tree` 语义）。上一轮
   留在 `build/lib` 里的旧 hash 文件会和这次的新文件**一起进 wheel**，界面
   看着正常却混着两代产物。`python -m workbench.build` 在构建前物理清掉
   `build/lib`，`check_wheel` 的「index.html 引用缺失资源」断言是第二道闸。

**为什么不在安装时构建**：`build-system.requires` 只能声明 Python 包，没有
PEP 517 钩子能装 Node；让 `pip install` 跑 npm 会让 Windows 用户装不上，
也让安装耗时与网络依赖不可控。业界做法（JupyterLab / Panel / Gradio）一致：
在 CI 里构建、把产物打进 wheel，用户端零 Node。

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

**跨栈测试为何伪造 dist 而不是真构建**：这样 `gates-and-tests` job 的静态托管
用例不需要真产物（它们自己造 `tmp_path/static`）。真产物由独立的 `wheel` job
验证——那一 job 复刻用户的安装路径。

## 7. CI 结构

两个 workflow，职责分开：

```yaml
# ci.yml —— 每次 push / PR
jobs:
  gates-and-tests:    # 装依赖 → python -m workbench.build → make check → make test
  wheel:              # 同样的构建 → python -m build --wheel → check_wheel
                      # → 干净 venv 装 wheel → 起服务 → 断言首页是真界面

# release.yml —— 打 v* tag（或手动触发）
jobs:
  build-and-release:  # 同上构建与断言 → 上传 wheel 到 GitHub Release
                      # 资产的固定副本名让 /releases/latest/download/ 长期有效
```

三个要点：

- **`wheel` job 是「装完没界面」这一类问题的唯一机械守卫**。它模拟的是
  「干净机器 `pip install` 这个包」——CI 里其余 job 都刚跑过构建，产物就在
  树上，永远看不见缺失。2026-11-26 发现的正是这个盲区：CI 只跑构建、
  从不打包，于是打出没有 `static/` 的 wheel 也没人知道。
- **`release.yml` 是分发的唯一出口**。前端产物不入库（§8），所以「自带界面
  的包」只能由 release 产出；源码安装需要 `python -m workbench.build` 一次。
- **不引入 `ci-ok` 聚合 job**：当前没有路径过滤（两个 job 每次都跑），
  required check 不会因跳过而永久 pending，聚合层没有收益。若将来加
  `dorny/paths-filter`，则必须补上 always-run 的聚合 job。

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
