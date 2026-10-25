# 桌面一键启动与前后端联通（3.2.0，2026-10-25）

## 问题

安装桌面应用后，本机服务（PostgreSQL / Elasticsearch / API / worker）需要一个 `local-runtime install` 步骤；应用启动时在后台跑 `ensure`，但没有可见进度，前端在服务就绪前就请求接口，表现为空白或“一直在读取模型设置”。用户必须自己开终端或等很久，不像成熟应用。

## 现在的行为

1. **启动页**（`web/src/features/desktop/DesktopGate.tsx`）：检测桌面环境，显示四个阶段（准备组件 / 数据库与检索 / 研究服务 / 连接界面）。
2. **首次启动二选一**：`完整安装（含全文检索，约 1.2 GB）` 或 `精简安装（不含检索，约 400 MB）`。选择写入 `localStorage`，之后双击自动按该模式拉起。
3. **进度可见**：`local-runtime` 在下载、解压、`initdb`、启动数据库、启动 API 各阶段写入 `runtime.json`（`state` + `progress`），Rust `research_status` 读取并对 TCP 端口做存活探测，前端每 1.5 秒刷新。
4. **一键控制**：`research_start`（未安装则 `ensure`，已安装则 `start`）、`research_stop`、`research_open_logs`；连接结果在 Rust 侧缓存，避免每次请求都启动 127 MB 的 packaged backend。
5. **失败可恢复**：显示错误码、`重试启动`、`打开日志目录`；也可以「连接已有服务」填地址与密钥，直接连远程 `scriptorium research serve`。
6. **连接后进入工作台**：`get_research_connection` 返回 URL 与 API key，前端重置连接缓存后挂载工作台，后续请求全部带 Bearer。

## 验证

| 检查 | 结果 |
|---|---|
| DESKTOP-01 首次启动显示一键安装选项 | 通过（截图 `12-desktop-first-run.png`） |
| DESKTOP-02 精简安装以 `search=false` 启动 | 通过（`research_start(search=false)`） |
| DESKTOP-03 显示安装/启动进度 | 通过（截图 `13-desktop-progress.png`） |
| DESKTOP-04 服务就绪后自动进入工作台 | 通过 |
| DESKTOP-05 前端与后端连接畅通 | 通过（项目列表经 8010 返回） |
| DESKTOP-06 启动失败给出错误与重试 | 通过（截图 `14-desktop-failed.png`） |

- `scripts/desktop_bootstrap_check.py` 用**假 Tauri 桥**驱动上述流程，不下载任何依赖（6/6）。
- `cargo check` 通过；`npm run build` 与 `oxlint` 通过。
- 安装包：3.2.0 NSIS 124.12 MiB / MSI 125.41 MiB，在 sidecar 修复后重打（`output/desktop-build-320e.log`）。

## 真实本机运行验证（2026-10-25 12:27）

在开发机上用**真实的本地运行时**（`%LOCALAPPDATA%\Scriptorium\research`，PostgreSQL 17.6 + Elasticsearch 8.19.3，端口 55433/59201/50368）跑通了启动流程：

| 阶段 | 观察 |
|---|---|
| `local-runtime start` | `runtime.json` 依次写入 `starting/postgres` → `starting/schema` → `starting/api` → `running/done` |
| `/health` | `200 {"status":"ok","search":"enabled"}` |
| `local-runtime connection` | 返回 URL 与 API key；带 Bearer 调 `/api/v2/projects`、`/api/v2/system/model` 均 200 |

期间修掉两个会阻断一键启动的问题：

1. **打包缺少 `unicodedata`**：`httpx`/`idna` 在健康检查时触发 `ModuleNotFoundError`，本机服务永远到不了 `running`。已在 `scriptorium.spec` 的 hiddenimports 补 `unicodedata`、`idna` 并重建 sidecar。
2. **启动失败只剩错误名**：`run()` 现在附带一行 stderr 摘要（不含参数/密钥），并检查 PostgreSQL 子进程是否已退出，失败时给出日志尾部而不是笼统的 `psql.exe`。

## 未验证

- **没有真实执行首次下载**（PostgreSQL 约 350 MB、Elasticsearch 约 600 MB）：本机运行时是此前已安装的依赖，本次验证的是启动与连接；全新机器上的下载/解压/`initdb` 仍未实测。
- 未在干净 Windows 机器上安装 3.2.0 走完整首启流程；未验证断网/磁盘不足的提示文案。
- 精简模式（无 Elasticsearch）在本机服务里的端到端行为已在 2026-10-25 的部署记录中验证（API 侧），桌面侧未重跑。
