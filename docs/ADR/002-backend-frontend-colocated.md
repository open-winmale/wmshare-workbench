# ADR-002 · 前后端同仓，布局 `backend/` + `frontend/`，产物进 wheel

- **日期**：2026-11-25
- **状态**：`accepted`
- **决策者**：项目负责人
- **关联工作项**：架构重构（P0 收口）

## 背景

项目同时需要 Python 数据层（wmshare SDK 之上）与 Web 呈现层。落地前必须先定三件事：
① 同仓还是分仓 ② 目录怎么摆 ③ 前端产物怎么到用户手里。

这三个决定都是**高迁移成本**的：一旦代码写起来，改布局要全局 sed，改交付方式要重做 CI。
所以先用兄弟仓的实证来定。

## 调研：四个兄弟仓的实价

| 仓 | 布局 | 产物去向 | CI | 契约 |
|---|---|---|---|---|
| `wmshare-tools` | `src/bigwinner/` + `web/` | vite `outDir` 直写 Python 包 | 两并行 job，无 `needs` | 手写 `types.ts`，无检查 |
| `investing` | `src/` + 两个 Go sidecar | nginx 整合 | 单 job，不测后端 | 手写 + markdown |
| `sift` | 纯前端，直连远端 API | GH Pages | `build` ‖ `e2e` | 手写 |
| `winmale-v2` | 纯前端 | **独立仓** `winv2` | 需 clone 第三仓 | proto submodule |

**`wmshare-tools` 已踩的 6 个坑**（有 CHANGELOG 记录）：

1. `web_dist/` 被 gitignore 且不在 `package-data` → `pip install` 拿到的包
   **既无新 UI 也无旧 UI**。修复是加启动横幅，根因未解。
2. 三处版本号（`pyproject` / `__init__` / `package.json`）手同步，**已漂移过一次**
   （CHANGELOG 1.7.1：`web/package.json` 停在 1.6.0）。
3. 未构建时**静默回退旧界面**，用户误以为拿到旧版。
4. 用「产物存在」当构建状态，重建要手 `rm -rf`。
5. 契约 `types.ts` 注释称「与 17 个 handler 一一对应」，**无测试保证**。
6. 两套 `JSON.stringify` 键规范化手同步（TS + Python），无桥接测试。

**`winmale-v2`/`winv2` 分仓的实价**：

- 一次 API 变更 = **三仓提交**（proto → 前端生成 → 后端生成）
- 后端 `gen-all.sh` **写仓外文件** 231KB（`../winmale-v2/src/features/...`），
  diff 落在错误仓库，且**无 `--check` 漂移门禁**
- vite 里 ~50 行手写插件，只为让 `@/` 按导入方分流；缺 sibling 时静默降级
- CI 必须 `git clone` 第三个仓
- `dev.sh` 要 `go run` 后端仓才能拿到 JWT
- `KNOWN_ISSUES.md` 仍引用早已抽走的 `backend/`

**结论：分仓在付租金，且没有技术理由**——分仓本为「多人/多部署单元」的隔离，
本项目是本地单用户工具，两半永远同版本发布。

## 决定

### ① 同仓

不采用分仓。理由见上。

### ② 布局 `backend/` + `frontend/` 平级

不跟 `wmshare-tools` 的 `src/` + `web/`。

**理由**：`src/` 暗示「Python 是本体、前端是附属」；两半都重要，用对称命名表达。
多数派做法也是平级——FastAPI 官方模板、Superset（`superset/`+`superset-frontend/`）、
Label Studio（`label_studio/`+`web/`）。

**不套 `src/`**：`backend/` 本身已是源布局隔离层（里面只有 `workbench` 一个包，
从仓库根 `import workbench` 本就失败）。再套是两层包装干同一件事，
且门禁报错路径多一级噪声。packaging 安全靠 `check_wheel` 的真断言，不靠目录结构提醒。

**`frontend/src/` 保留 `src`**：Vite/tsconfig 约定（`index.html` 在根、代码在 `src/`），
不是自由选择。

**`tools/` → `gates/`**：两个同名 `tools/` 导致过真实 bug（`check_envelope` 扫错目录，
真实 handler 完全不被检查）。

### ③ 产物进 wheel

`vite outDir` 直写 `backend/workbench/static/`，`package-data` 覆盖它，
CI 断言 wheel 内含 `static/index.html`。

**理由**：用户 `pip install` 就该有界面，**不该装 Node**。这也是 JupyterLab /
marimo / Superset 的共同做法（源码安装才需要 Node，预构建 wheel 不需要）。

**明确不做**：
- 不做旧界面回退（`wmshare-tools` 的静默降级会让用户以为拿到旧版）
- 不把 `dist/` 提交入库（每次改前端产生巨大 diff；git 官方文档把构建产物列为
  `.gitignore` 典型用例）
- 不在 install 时构建（PEP 517 只隔离 Python 构建依赖，`npm` 不在其内；
  sdist 安装会强制用户在本地装 Node）

### ④ 路由用 hash

后端因此只需托管 `/` 与 `/assets/*`，无需 SPA fallback。

## 后果

### 变好的

- 一次提交可同时改前后端 → 契约变更原子化
- 契约**生成 + 漂移门禁**（兄弟仓都没做到）→ 字段改名不会静默变成 `undefined`
- 版本三元同步门禁 → 堵死 `wmshare-tools` 漂移过的坑
- wheel 含 UI 且 `check_wheel` 断言 → 堵死「pip 装了没界面」
- CI 两 job 独立 + `wheel` 有 `needs` → 后端 job 不需要 Node，但交付物被验证

### 变差的（诚实列出）

- **与兄弟仓布局不一致**。新人需要读本 ADR 才知道为什么不跟 `wmshare-tools`。
  这是一个真实的认知成本。
- **`gates/` 改名**打断了指向 `tools/check_*.py` 的引用（本次已全量同步；
  当前无 CI 配置，影响面为零）。
- **hash 路由**使 URL 带 `#/`，不如 history 模式干净。
- **单仓双栈**意味着 `make check` 要同时管两套工具链（已用 `gates/` 全 Python
  实现门禁 + 前端只做 typecheck/build 来最小化）。

### 不可逆的部分

布局一旦写进 CI 与文档，改就是全局 sed。所以这个 ADR 必须在代码之前定。

## 需要同步更新的东西

- [x] `docs/ARCHITECTURE.md`（新建）
- [x] `docs/PROJECT_SPEC.md` §2 分层双栈化
- [x] `quality/baselines/imports.json` → version 2 双套
- [x] `pyproject.toml`（`where`、`package-data`、`pytest pythonpath`）
- [x] `.gitignore`
- [x] `Makefile` 改真 make
- [x] `gates/` 路径常量与扫描面
- [x] `tests/test_gates_selftest.py` 路径 + 新增 14 个用例

## 复审触发条件

1. 若前端需要独立发版（如做成可嵌入 SDK），考虑拆包或分仓
2. 若引入第二个前端（如移动端），`frontend/` 需改为 `frontend/` 下多应用
3. 若 `backend/` 需要发布多个独立分发包，改 `backend/packages/<pkg>/`
4. 若 hash 路由的 URL 形态被证明影响使用（分享链接、截图），改 history + fallback
