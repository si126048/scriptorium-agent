# 部署指南

Scriptorium 有两种运行时：**研究工作台**（PostgreSQL，可选 Elasticsearch）和**本地单机**（SQLite，零外部服务）。本文覆盖工作台的部署；单机运行时只需 `pip install -e .`。

## 选择一种方式

| 方式 | 适合 | 需要 | 启动 |
|---|---|---|---|
| **Docker Lite** | 试用、单机、最省事 | Docker | `docker compose -f compose.research.lite.yml --env-file .env.compose up -d --build` |
| **Docker 完整** | 需要全文检索 | Docker（多 1 GB 内存） | `docker compose -f compose.research.yml …` |
| **Docker 团队** | 多人、OIDC、审计 | Docker + Keycloak | 见 [compose.team.yml](../compose.team.yml) 与 [团队部署](#团队部署) |
| **原生** | 已有 PostgreSQL / 开发 | Python 3.12、Node 20+（构建前端） | `python scripts/quickstart.py --native --database-url …` |
| **桌面安装包** | 不想开终端 | Windows | `src-tauri/target/release/bundle/nsis/*.exe`（需自行构建） |

所有方式都只把 API 绑定到 `127.0.0.1`，默认不需要登录；对外提供服务时请阅读 [安全](#安全)。

## 一条命令：Docker Lite

```bash
python scripts/quickstart.py --check          # 先看本机是否具备条件
python scripts/quickstart.py --docker         # 生成 .env.compose、构建、等待健康、打印地址
```

等价的原始命令：

```bash
cp .env.compose.example .env.compose          # 修改 SCRIPTORIUM_POSTGRES_PASSWORD
docker compose -f compose.research.lite.yml --env-file .env.compose up -d --build
open http://127.0.0.1:8010                    # 首次构建约 3–6 分钟
```

Lite 模式不启动 Elasticsearch：检索接口返回 `503 SEARCH_DISABLED`，「提问即研究」会自动改用项目材料扫描，并在回答里标注 `warning=SEARCH_DISABLED`。想启用全文检索：

```bash
python scripts/quickstart.py --docker --with-search
# 或
docker compose -f compose.research.yml --env-file .env.compose up -d --build
```

数据在命名卷 `research-pg`、`research-objects`（完整模式另有 `research-es`）中，`down` 不会删除；`down -v` 才会。

## 原生部署（只需要 PostgreSQL）

```bash
python scripts/quickstart.py --native \
  --database-url 'postgresql+psycopg://scriptorium:password@127.0.0.1:5432/scriptorium'
```

脚本会：创建 `.venv` 并安装 `.[research]` → 构建 `web/dist`（缺失时）→ 执行 `init-db` → 启动 worker 与 API，前台运行，Ctrl+C 同时停止两者。

手工等价步骤：

```bash
python -m venv .venv
.venv/bin/pip install -e ".[research]"        # Windows: .venv\Scripts\pip
npm --prefix web ci && npm --prefix web run build
export SCRIPTORIUM_DATABASE_URL='postgresql+psycopg://…'
export SCRIPTORIUM_OBJECT_ROOT="$PWD/output/research-objects"
scriptorium research init-db
scriptorium research serve                    # 终端 1 → http://127.0.0.1:8010
scriptorium research worker                   # 终端 2
```

### 关键环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SCRIPTORIUM_DATABASE_URL` | 空（必填） | PostgreSQL 17；`postgresql+psycopg://user:pass@host:5432/db` |
| `SCRIPTORIUM_ELASTICSEARCH_URL` | `http://127.0.0.1:9200` | **设为空字符串即禁用检索**（索引与查询都跳过） |
| `SCRIPTORIUM_OBJECT_ROOT` | `./data/research-objects` | 原文/版本对象目录；生产环境放持久盘 |
| `SCRIPTORIUM_RESEARCH_API_KEY` | 空 | 非空时客户端需 `Authorization: Bearer <key>`；仅本机可留空 |
| `SCRIPTORIUM_RESEARCH_ORIGINS` | localhost 若干 | 允许的浏览器来源，逗号分隔 |
| `SCRIPTORIUM_RESEARCH_OWNER` | `local-user` | 单用户模式下的固定操作者 |
| `SCRIPTORIUM_MODEL_API_KEY` | 空 | 兼容旧配置；更推荐在工作台「研究模型」里保存 |
| `SCRIPTORIUM_OCR_ENGINE` | `auto` | `auto` / `tesseract` / `off`，扫描版 PDF 用 |

模型服务商也可以完全不配：先用「演示模式」走通流程，之后再在 **设置与档案 → 研究模型** 选择 DeepSeek / 通义千问 / OpenAI / Moonshot / 智谱 / 本机 Ollama / 自定义端点，密钥存系统凭据或私有文件，接口不回显。

## 首次使用

1. 打开 `http://127.0.0.1:8010`，**＋ 项目** 新建项目。
2. **导入材料**：TXT / Markdown / PDF（扫描版走 OCR）/ TEI。导入是异步任务，状态变为「就绪」即可阅读。
3. 在对话框直接提问（默认），或选方法（构境 / 内在批判 / 视差 / 理论视角比较）。演示模式不产生学术结论。
4. 回答里的「原文 N」回到精确锚点；「深入完整研究」把同一冻结范围交给完整流水线。
5. 文稿区写作、插入引用与脚注，导出 Markdown / JSON / TEI / DOCX（Pandoc 首次导出时下载固定版本到缓存目录）。

## 团队部署

`compose.team.yml` 包含 PostgreSQL、Elasticsearch、Keycloak、Caddy 与 API/worker，所有端口不对外发布，由 Caddy 终止 TLS。按 [deploy/team/team.env.example](../deploy/team/team.env.example) 准备域名、数据库密码与管理员 OIDC subject，再：

```bash
docker compose -f compose.team.yml --env-file .env.team up -d --build
```

首次登录后由管理员在「项目治理」里分配负责人 / 研究者 / 评议者 / 只读角色。外部模型调用受预算与敏感材料策略限制，记录在模型调用账本中。

## 备份与升级

- **数据库**：`docker compose … exec postgres pg_dump -U scriptorium scriptorium > backup.sql`；恢复用 `psql`。原生部署直接 `pg_dump`。
- **对象**：备份 `research-objects` 卷（或 `SCRIPTORIUM_OBJECT_ROOT` 目录）与数据库同一时点。
- **升级**：拉新代码后 `docker compose … up -d --build`，`migrate` 服务会执行 `init-db`（幂等迁移）；原生部署重新 `pip install -e ".[research]"` 后 `scriptorium research init-db`。
- 迁移与对象必须成对恢复；不要用旧程序打开新库。

## 桌面安装包

安装后的桌面应用是**一键启动**：双击 → 首次选择「完整/精简安装」→ 应用自动下载依赖、初始化数据库、启动 API 与 worker → 进入工作台。进度页显示阶段，失败给出错误码、重试与日志目录；也可改用「连接已有服务」。

- 本机数据：`%LOCALAPPDATA%\Scriptorium\research\`（数据库、对象、日志、下载的依赖）。
- 应用设置：`%APPDATA%\app.scriptorium.desktop\settings.json`。
- 停止服务：启动页「停止本机服务」，或 `scriptorium-backend.exe local-runtime stop`。
- 卸载应用不会删除研究数据；需要时手动删除上述目录。

构建安装包（开发者）：

```bash
npm --prefix web ci && npm --prefix web run build
pwsh scripts/build-sidecar.ps1        # PyInstaller 打包后端（约 5 分钟）
cd src-tauri && cargo tauri build     # NSIS / MSI 到 src-tauri/target/release/bundle/
```

新克隆没有 `src-tauri/bin/`，直接 `cargo check` 会报缺少 sidecar；先构建 sidecar 即可。CI 不构建桌面。

## 安全

- 默认绑定 `127.0.0.1`，只允许本机访问。
- 对外暴露必须：设置 `SCRIPTORIUM_RESEARCH_API_KEY`、放在 HTTPS 反向代理后（Caddy/Nginx）、限制来源并定期备份。
- 模型密钥保存在操作系统凭据库或权限 0600 的私有文件；接口只返回「已配置 / 来源」，从不回显。
- 团队模式使用 OIDC，不在本机保存共享密码；`SCRIPTORIUM_ADMIN_SUBJECTS` 指定管理员。

## 排错

| 现象 | 处理 |
|---|---|
| `/health` 不通 | `docker compose … logs api`；首次构建未完成或迁移失败 |
| `503 SEARCH_DISABLED` | 预期：Lite 模式无 Elasticsearch；用 `--with-search` 或配置 `SCRIPTORIUM_ELASTICSEARCH_URL` |
| 回答提示 `SEARCH_UNAVAILABLE` | Elasticsearch 配了但连不上；修复服务或改为空值（自动材料扫描） |
| `MODEL_NOT_CONFIGURED` | 没有可用模型密钥；设置页保存密钥，或改用演示模式 |
| 浏览器 CORS 报错 | 把实际访问来源加入 `SCRIPTORIUM_RESEARCH_ORIGINS` |
| 端口 8010 被占用 | `--port 8011`（原生）或修改 compose 的端口映射 |
| `docker compose` 报缺少变量 | 使用 `--env-file .env.compose`，并确认密码是 URL 安全字符 |

部署相关的验收记录在 [docs/acceptance/](acceptance/)；研究服务的 API 与错误码见 [research-service.md](research-service.md)。
