# 部署简化与精简记录（2026-10-25）

目标：让新克隆仓库的使用者用一条命令启动研究工作台，并去掉仓库里不再使用的界面代码。

## 改动

| 方面 | 内容 |
|---|---|
| 一键启动 | 新增 `scripts/quickstart.py`：`--check` 环境诊断；`--docker` 生成 `.env.compose`、构建并等待 `/health`；`--native` 建 venv、装依赖、建库、起 API + worker |
| 最小部署 | 新增 `compose.research.lite.yml`：PostgreSQL + migrate + api + worker，**不含 Elasticsearch** |
| 检索可选 | `SCRIPTORIUM_ELASTICSEARCH_URL` 为空即禁用索引与检索；`/health` 返回 `search: disabled`，`/search` 返回 503 `SEARCH_DISABLED`，提问自动改用材料扫描并在回答中标注 |
| 部署文档 | 新增 `docs/deployment.md`（Docker Lite/完整/团队、原生、桌面、备份升级、排错）；README 顶部改为三条启动路径 + 首次使用 + 配置表 |
| 精简前端 | 删除未引用的旧界面 18 个文件（chat / sidebar / settings / topostyle / research workbench / lib store、api，约 3.9k 行）；`scriptorium/static/index.html` 由 62 KB 旧控制台换成构建提示页 |
| CI | 新增 deployment job：校验两份 compose 清单 + quickstart 诊断 |

## 验证

- **无 Elasticsearch 端到端**：独立数据库 + 新 worker，`/health` = `search: disabled`；`/search` 返回 `503 SEARCH_DISABLED`；导入材料后提问成功，记录 `plan.retrieval=material_scan`、`warning=SEARCH_DISABLED`，4 段材料被读取。
- **原生一键启动**：`scripts/quickstart.py --native --database-url … --port 8011` 完成 `init-db` → worker → API → `/health` 200 → 打印工作台地址；Ctrl+C 路径由脚本 `finally` 终止两个子进程。
- **compose 清单**：PyYAML 解析通过；lite 服务为 api/migrate/postgres/worker，完整版另含 elasticsearch。
- **前端**：`npm run build` 通过（主包 299 KB），`oxlint` 0 告警；`tsc` 通过。
- **测试**：**383 passed**（新增 2 项检索禁用单测；旧静态界面断言改为工作台访谈面 + 构建提示页）。
- **Ruff**：`scriptorium tests scripts migrations` 全通过。

## 未验证

- 本机没有 Docker：`compose` 只做了清单解析，未实际构建镜像或启动容器；CI 的 deployment job 会执行 `docker compose config`。
- 未在干净机器上跑 `clone → quickstart --docker` 全流程。
- `quickstart --native` 的 venv 安装步骤（`pip install -e .[research]`）本次用 `--no-install` 跳过，安装耗时未计时。
