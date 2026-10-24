# 研究工作台运行、迁移与恢复

本开发版保留旧版功能，新增研究服务、阅读器、构境、内在批判、视差与研究对象编辑。实际验证范围与未完成项见 [统一工作台验收文档](acceptance/scriptorium-unified-workbench-acceptance.md) 与 [早期实施状态](plans/scriptorium-implementation-status.md)。

## 1. Windows 本机启动

准备可连接的 PostgreSQL 17 与 Elasticsearch 8.19，先创建独立空数据库，例如 scriptorium。无需安装 Docker；也可使用下一节的容器配置。

在项目根目录安装：

```powershell
python -m pip install -c requirements-research.lock '.[research,dev]'
```

参考 `.env.research.example` 配置环境或项目 `.env`。不要覆盖已有 `.env`；添加研究配置即可。URL 密码含特殊字符时必须 URL 编码。

```powershell
$env:SCRIPTORIUM_DATABASE_URL = 'postgresql+psycopg://scriptorium:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:5432/scriptorium'
$env:SCRIPTORIUM_ELASTICSEARCH_URL = 'http://127.0.0.1:9200'
$env:SCRIPTORIUM_OBJECT_ROOT = 'D:\ai\scriptorium\data\research-objects'
python -m scriptorium.research.cli init-db
```

构建界面：在 `web` 目录执行 `npm ci`、`npm run build`，然后回到项目根目录。

两个终端使用相同研究配置分别启动：

```powershell
python -m scriptorium.research.cli serve
```

```powershell
python -m scriptorium.research.cli worker
```

浏览器打开 [研究工作台](http://127.0.0.1:8010)。在“服务与任务”配置服务地址和密钥。未配置密钥的模式仅接受本机访问；远程必须设置 `SCRIPTORIUM_RESEARCH_API_KEY`，并使用 HTTPS 反向代理。固定单人身份不是多人登录系统。

一条命令启动（Docker，无需 Elasticsearch）：`python scripts/quickstart.py --docker`；完整选项、团队部署与排错见[部署指南](deployment.md)。也可用 `scripts/start-research.ps1 -Mode serve/worker/init-db`（脚本不负责数据库服务）。

研究模型不绑定单一服务商：可选通义千问、DeepSeek、OpenAI、Moonshot、智谱 GLM、本机 Ollama 或任意 OpenAI 兼容端点。可在工作台“设置与档案 → 研究模型”里选择服务商、填写接口地址与模型、保存密钥并测试连接；也可继续用环境变量（`DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`MOONSHOT_API_KEY`、`ZHIPU_API_KEY`、`SCRIPTORIUM_MODEL_API_KEY`）。密钥与配置细节见 3.2。没有密钥时可以显式选择“演示流程”，演示不产生学术结论。未对真实服务商调用做质量验收。

## 2. 可选 Compose 部署

设置 `SCRIPTORIUM_POSTGRES_PASSWORD`、`SCRIPTORIUM_RESEARCH_API_KEY`；使用 URL 安全字符，不使用示例占位符。

```powershell
docker compose -f compose.research.yml up --build -d
```

配置包含 PostgreSQL、Elasticsearch、数据库迁移、API 和 Worker，仅 API 的 8010 端口映射到宿主回环地址。原有 `docker-compose.yml` 保持原用途。此环境没有 Docker 引擎，因此本轮未执行镜像构建和容器启动验证。

## 3. 日常研究流程

1. 新建研究项目，导入 TXT、Markdown、文本型 PDF 或项目 TEI 子集。
2. 等待后台任务完成，选择材料和文本版本。
3. 选中文字，保存证据，填写笔记并保存。
4. 可以在多个材料中勾选片段，进入方法分析；未勾选时使用当前材料。
5. 输入问题，选择构境、内在批判或视差。查看结果中的证据、覆盖范围与未决问题。
6. 在构境比较中查看竞争档案；在论证或视差页面编辑结构对象。
7. 在文稿页面关联论点，保存文稿并导出 Markdown、JSON 或 TEI 标注。

### 3.1 直接提问（默认）

对话框默认就是“提问”：不需要先勾材料、也不需要选方法。输入问题后服务会：

1. 用项目检索（Elasticsearch，CJK 分析器）找相关片段；检索不可用或没有命中时，退回到已就绪材料的顺序扫描，并在回答记录里写明 `plan.retrieval` 是 `search` 还是 `material_scan`；
2. 只读选定的窗口（默认最多 8 段、24,000 字符），放不下的窗口记为 `unread`，不静默截断；
3. 只依据这些材料回答，每个事实判断都附逐字引文；引文用 code point 半开区间对齐，重复引文用 prefix/suffix 消歧，定位不唯一就报错，绝不猜测；
4. 生成 `research_answer` 记录（含 `scope`、`plan`、`coverage`、`open_questions`、`followups` 与调用用量），并在对话里给出回答正文与“原文 N”按钮。

选中的材料或选区会收窄范围（`plan.retrieval=explicit`）；回答卡片上的“深入完整研究”会把同一冻结范围交给完整方法流水线（构境／内在批判／视差／审查）。演示模式只说明读了哪些材料，不产生学术结论；真实模式缺少模型密钥时任务失败并报 `MODEL_NOT_CONFIGURED`，不会退回演示。

相关错误码：`NO_MATERIALS_FOR_QUESTION`（项目里没有可读材料）、`ANSWER_REQUIRES_CITATION`（有事实判断却没有任何引文）、`ANSWER_CLAIM_REQUIRES_CITATION`（某条判断缺引文）、`CITATION_AMBIGUOUS`／`CITATION_EXACT_QUOTE_NOT_FOUND`（摘录无法唯一定位）、`SEARCH_UNAVAILABLE`（会记录并退回材料扫描）。

### 3.2 模型服务商与密钥

工作台“设置与档案 → 研究模型”支持多个 OpenAI 兼容服务商：

| 服务商 | 默认接口 | 默认模型 | 环境变量 |
|---|---|---|---|
| 通义千问（DashScope） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | `DASHSCOPE_API_KEY` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | `DEEPSEEK_API_KEY` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | `OPENAI_API_KEY` |
| Moonshot（Kimi） | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | `MOONSHOT_API_KEY` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | `ZHIPU_API_KEY` |
| Ollama（本机） | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` | 无需密钥 |
| 自定义端点 | 自行填写 | 自行填写 | `SCRIPTORIUM_MODEL_API_KEY` |

- 保存后立即切换到该服务商；接口地址与模型会记住，可在同一表单里改。
- **密钥位置**：Windows 默认写入当前用户的系统凭据（Credential Manager）；非 Windows 或设置 `SCRIPTORIUM_KEY_STORAGE=file` 时写入私有文件（`SCRIPTORIUM_HOME`／`%APPDATA%\Scriptorium` 下的 `provider-keys.json`，POSIX 权限 0600）。接口只返回“已配置／来源”，从不回显密钥。
- 环境变量始终可用作后备；保存的密钥优先于环境变量。`SCRIPTORIUM_PROVIDER` 可指定默认服务商，`SCRIPTORIUM_MODEL` 可覆盖模型。
- “测试连接”只调用服务商的模型列表接口（列出模型），不发送研究材料，不需要额度消耗；失败返回 `PROVIDER_PROBE_FAILED:<错误>`，不打印密钥。
- 旧 CLI／ACP／MCP 运行时在未显式传参时也跟随当前服务商；显式传入 `api_key`／`base_url` 时保持原有行为。
- **桌面模式**：工作台启动时只向桌面进程询问一次本机服务地址（2.5 秒超时）；取不到就回退到 `http://127.0.0.1:8010` 并在设置页显示提示，不会出现“正在读取模型设置…”无限等待。桌面命令本身也有 8 秒超时，慢速或缺失的本机运行时只影响写提示，不阻塞界面。
- 相关错误码：`UNKNOWN_PROVIDER`、`PROVIDER_KEY_REQUIRED`、`INVALID_PROVIDER_KEY`、`INVALID_PROVIDER_BASE_URL`、`PROVIDER_BASE_URL_REQUIRED`、`MODEL_NOT_CONFIGURED`。



未发送的对话输入与文档临时编辑保存在当前浏览器；文档区显示“未保存修改”或“与已保存版本一致”，两者不混同。切换会话、刷新或另一窗口先写入后再返回时，工作区会取回最新 revision 重试保存，标题、正文与未发送输入仍可恢复。已保存的修订写入数据库并以修订号区分。

材料存在两个以上文本版本时，原文区可“比较上一版”：按 `xml:id` 逐段对照修改、新增与删除，旧版引用保持原段落位置，不随修订移动。

方法调用默认 30,000 输入字符、4,000 输出 token。不能容纳的完整片段记为未覆盖；首版没有自动长文分批研究，不承诺读完所有材料。

TEI 校验失败或 PDF 无文本时原件仍保留，可下载原件、修正后重试。PDF 页标识为提取页序，不能自动当作印刷页码。

扫描件 OCR 使用本地引擎，结果保存为新的不可变文本版本并标记为待校核。材料的 `metadata.ocr` 记录 `succeeded`／`failed`、语言、空页列表、未能识别的页与失败错误码；失败时原版本保持不变，原件始终可下载。已有的文本层会被保留，只有无文本的页面送去识别：混合文档仍产出可读版本，同时把未识别页列入 `empty_pages`／`ocr_unavailable_pages`；所有页面都无法识别时才整体失败，不会生成空文本版本，也不宣称识别质量通过。文本版本按修订链末端判定“最新”，同一秒内写入的多个版本不会互相覆盖顺序。

TEI 标注导出含引用摘录、版本 URN 和字符范围；它是交换文档，不能代替包含原件的完整备份。

## 4. 旧数据迁移

先停止旧 API／桌面应用的写入，确保正式迁移依据稳定快照。默认源位置包括：

- 项目 `data/lacan.db`，以及实际环境变量配置的其他路径。
- 桌面 `%APPDATA%\app.scriptorium.desktop\lacan.db`。
- PageIndex 若位于其他数据库，应单独盘点与迁移。

只读预览，不需要新数据库连接：

```powershell
python -m scriptorium.research.cli migrate-sqlite data/lacan.db --report output/migration-preview.json
```

审核统计后导入独立目标数据库：

```powershell
python -m scriptorium.research.cli migrate-sqlite data/lacan.db --apply --source-root D:\ai\scriptorium --report output/migration-applied.json
```

`--source-root` 可多次指定；只有在这些目录内的原件才允许自动读取。不要把整个磁盘设为根目录。目标库与源 SQLite 分离，命令不改写源记录。

报告包含全部源记录的计数、保存与跳过结果、项目映射、材料处理状态及证据定位异常。原始数据缺失、授权失效或引文不唯一时明确保留问题。涉及混合失效授权的项目采用保守阻断，原库仍保留，需另行整理合法材料；不能将这种情况描述为无损全自动迁移。

当前直接阅读格式限 TXT、Markdown、文本 PDF 和项目 TEI。旧库中的其他格式仍有兼容档案，但不保证可重新解析原件。

旧分析、访谈、Persona 和对话可在“历史档案”读取原结构。全部旧功能仍可从旧界面使用；它们没有全部转为新库上的可继续运行工作流。

浏览器聊天：在旧界面顶栏或新版“历史档案”点击导出，再向目标项目导入 JSON。导出不包含密钥，不删除本地记录，不能恢复早已被截断的消息。

迁移完成后执行索引重建；检查报告、抽样引用和项目归属，再正式切换。切换后新数据不会写回旧库，回退前先备份新库和对象。

## 5. 任务、索引与清理

任务失败在“服务与任务”查看错误码并重试。Worker 重启后会在租约到期后恢复未完成任务。取消不保证已经发给远程模型的请求立即停止计费。

API 与 Worker 必须来自同一版本。`GET /health` 返回 `version` 与 `job_kinds`，`python -m scriptorium.research.cli doctor` 返回同一份队列视图、当前数据库修订号（`schema_revision`）和对象存储配置。升级后先比较这两处再入队新任务。

旧 Worker 无法识别新任务类型时，会把任务**释放回队列**而不是标为失败：任务保持 `queued`、尝试次数不增加、只追加一条 `UNSUPPORTED_JOB_KIND` 事件，由当前版本的 Worker 继续处理。若在 `doctor` 的 `unknown_kind_jobs` 中长期看到某类任务，说明没有运行该版本的 Worker。

```powershell
python -m scriptorium.research.cli rebuild-index
python -m scriptorium.research.cli retry-index
python -m scriptorium.research.cli doctor
python -m scriptorium.research.cli verify-anchors --report output/anchor-check.json
```

`verify-anchors` 逐条重新核对证据锚点与不可变文本：可定位的计入 `located`，缺段落、引文不符或材料已撤回的列入 `problems`。正式切换前后用同一命令比对，已标为核验的引用必须全部可定位。

重建保留旧物理索引，不自动删除。索引错误最多自动处理三次，再由管理员检查后重排。

材料撤回立即阻断应用访问，删除相关可读文本、证据和派生记录，保留不含正文的标识。可能包含敏感正文的旧项目档案采用保守脱敏。共享内容键只有在没有合法引用后才允许清理。

```powershell
python -m scriptorium.research.cli gc
python -m scriptorium.research.cli gc --apply
```

默认对象保留 24 小时。清理不能抹除已经下载的文件和旧备份；自行设置备份保留期。材料撤回意图会追加到对象根目录 `withdrawals.jsonl`，恢复会自动重放当前部署和备份内的清单，完成前不开放服务。跨机器恢复旧备份时必须同时携带原部署最新撤回清单；旧备份本身无法知道后来发生的撤回。

## 6. 备份与空库恢复

```powershell
python -m scriptorium.research.cli backup output/research-backup-20261024
```

目标目录必须不存在。备份使用一致性事务和研究表共享锁，期间研究写入等待；包含 JSONL 表数据、引用的对象和完整性清单，不包含服务密钥。备份本身包含研究正文，应作为私密档案保存。

将连接切换到新的空数据库，运行 init-db 后：

```powershell
python -m scriptorium.research.cli restore output/research-backup-20261024
python -m scriptorium.research.cli rebuild-index
```

跨机器恢复可追加 `--withdrawal-ledger D:\backup\latest-withdrawals.jsonl`。恢复前停止 API 与 Worker，检查 `withdrawals_replayed` 和清单，完成核验后再开放访问。

恢复拒绝非空研究表，验证表文件、对象散列和记录数，导入失败回滚数据库；撤回重放失败时必须排除故障后才可开放服务。失败过程中写入的无引用对象可稍后 gc。恢复时将未完成任务重新排队，取消请求保留为取消；索引重新构建。

## 7. 开发验证

测试数据库必须是可丢弃 PostgreSQL 库；每项集成测试创建并删除独立 schema。Elasticsearch 也必须为独立测试节点，测试会重建研究索引。

```powershell
$env:SCRIPTORIUM_TEST_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/scriptorium_test'
$env:SCRIPTORIUM_TEST_ELASTICSEARCH_URL = 'http://127.0.0.1:9200'
python -m pytest tests -q
python -m ruff check scriptorium/research migrations/research tests/test_research_texts.py tests/test_research_integration.py tests/test_unified_workspace.py tests/test_research_s3.py
```

没有集成服务配置时，相关测试明确 skip；skip 不能报告为真实服务验证通过。前端执行 `npm run build`、`npm run lint`；桌面执行 `cargo check --manifest-path src-tauri/Cargo.toml`。

可选的验收脚本（不会读取或写入正式研究库）：

```powershell
pwsh scripts/test-services.ps1 -Action start      # 启动 tmp/ 下的回环 PostgreSQL 与 Elasticsearch
pwsh scripts/test-services.ps1 -Action status
pwsh scripts/s3-test-endpoint.ps1 -Action start   # 启动回环 S3 兼容服务（SeaweedFS，端口 49000）
pwsh scripts/run-acceptance.ps1                  # pytest、专项套件、ruff、前端构建与检查、cargo check，逐项留日志
python scripts/worktree-digest.py --json          # 被验收工作区的文件散列，不能只用 Git HEAD 标识未提交代码
python scripts/browser_acceptance.py --material fixtures/research/autonomy-a.md
python scripts/snapshot-source.py --source data/lacan.db --out output/migration-freeze
```

`run-acceptance.ps1` 在 `output/acceptance/<时间戳>/` 写入 `environment.json`、每步日志、`summary.md`、`summary.json` 与 `source-database.txt`；后者记录 `data/lacan.db` 在运行前后的散列（含 `-wal`/`-shm`），一旦被写入即在本轮摘要中标出。跳过项与失败项分别记录，不会把 skip 计为通过。`browser_acceptance.py` 使用本机 Chromium/Edge 无头模式打开同一个 8010 地址，逐项检查统一入口、材料导入、选区笔记、原文回跳、草稿恢复、演示模式回复、单版本时的对照限制、版本对照、窄屏切换、跨项目隔离与导出，并保存截图和 `browser-acceptance.json`。

续验规则：源库或代码在验收期间发生变化时，运行失败；正常完整验收中出现测试跳过也返回失败。`summary.json` 的 `automated_verification_complete` 仅表示本轮配置的自动检查完整通过，不代表学术评议、系统重启或正式切换通过。新生成的记录仅保存脱敏后的连接地址。

进程恢复演练：将 `SCRIPTORIUM_DATABASE_URL` 指向允许创建验收 schema 的独立测试库，执行 `python scripts/restart-drill.py --lease-seconds 6`。脚本创建独立 schema 和对象目录，使用合成材料与显式演示模式，在检查点提交后终止自己创建的 Worker，再启动新 Worker 检查恢复、产物去重与完成消息；结果写入 `output/restart-drill/drill_<ID>/`。它不重启操作系统，不领取其他 schema 的任务，也不代替真实模型验收。默认生产租约仍为 300 秒；`SCRIPTORIUM_LEASE_SECONDS`、`SCRIPTORIUM_MAX_ATTEMPTS` 必须是正整数。

真实 S3 由 `tests/test_research_s3_live.py` 验证（需 `SCRIPTORIUM_TEST_S3_ENDPOINT`，默认 skip）：上传、读取、同内容不重建、篡改检出、非法键、错误桶、服务导入、备份与空库恢复。它使用本机 SeaweedFS 网关，属于真实 S3 协议实现，但仍不是机构对象存储；版本控制、保留策略、复制与 IAM 需在目标服务上另行验证。`tests/test_research_s3.py` 仅使用进程内替身，不能据此宣称真实对象存储已验收。

新克隆的仓库没有 `src-tauri/bin/`（构建产物，已忽略）：直接 `cargo check` 会报 `resource path bin\scriptorium-backend-x86_64-pc-windows-msvc.exe doesn't exist`，先 `npm --prefix web run build` 并运行 `scripts/build-sidecar.ps1` 即可。CI 只做 Python 与前端检查，不构建桌面。

桌面安装包：`powershell pwsh scripts/build-sidecar.ps1` 之后在 `src-tauri` 目录执行 `cargo tauri build`（首次会联网下载 NSIS/WiX），产物在 `src-tauri/target/release/bundle/`。若 `tauri.conf.json` 的 `beforeBuildCommand` 在当前 shell 下不可用，可先用 `npm --prefix web run build:tauri` 构建前端，再用 `--config` 覆盖该命令。

迁移演练与切换工具（只对冻结快照执行，不改写源库）：

```powershell
python -m scriptorium.research.cli migrate-sqlite <frozen>.db --apply --source-root D:\ai --report output/switch-rehearsal/apply.json
python -m scriptorium.research.cli verify-anchors --report output/switch-rehearsal/anchors.json
python scripts/migration-report.py --apply output/switch-rehearsal/apply.json --anchors output/switch-rehearsal/anchors.json --out output/switch-rehearsal/report.md
python scripts/sample-citations.py --count 20 --out output/switch-rehearsal/sampling.md
python -m scriptorium.research.cli backup output/switch-rehearsal/backup
```

`--source-root` 决定哪些目录中的原件允许被自动读取；不要把整个磁盘设为根目录。冻结源由 `SCRIPTORIUM_FROZEN_SOURCE` 保护：旧 `Store` 打开该路径会直接报 `SOURCE_DATABASE_READ_ONLY`，测试的默认库路径已移出 `data/`。

学术质量案例：

```powershell
$env:SCRIPTORIUM_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/scriptorium_quality'
python scripts/quality-cases.py --mode demo        # 仅验证流程，不产生学术结论
python scripts/quality-cases.py --mode live        # 需要 DASHSCOPE_API_KEY，产出待评议材料
```

脚本写入 `output/quality-cases/<时间戳>-<模式>/`：每案例材料与 `packet.json`、以及留空的 `review.md` 评议表（结论只能由研究者填写）。`--mode live` 缺少模型 key 时直接失败，不会退回演示。

## 8. 桌面服务模式

桌面端在研究连接设置保存地址后，下次启动不再自动启动旧 sidecar；“恢复桌面旧版启动方式”将恢复原行为。当前已运行的旧后端不会被强制终止。正式迁移前应退出旧桌面端。

桌面安装包本轮已实际构建：`src-tauri/target/release/bundle/nsis/` 与 `bundle/msi/`（3.1.0，各约 122 MiB，含 `scriptorium-desktop.exe` 与打包后的 `scriptorium-backend.exe`）。已验证 MSI 管理性解包、NSIS 静默安装/卸载，以及打包 sidecar 启动后 `/health` 返回版本与任务类型。安装包未签名，也尚未在干净机器上做 GUI 启动与系统重启验证；发布前仍需补这两项。

Python wheel 包含研究代码与 TEI 模式；Alembic 配置和迁移脚本当前以项目源码或研究镜像分发，因此数据库初始化从项目根目录执行。

## 9. Agent 体验升级：本机服务与恢复

2026-10-24 新增的本机服务入口为 `python -m scriptorium.desktop_entry local-runtime <操作>`，打包后为 `scriptorium-backend.exe local-runtime <操作>`。默认数据根目录为 `%LOCALAPPDATA%/Scriptorium/research`；`--root` 可用于隔离验收。不会迁移或打开旧 SQLite 库。

```powershell
python -m scriptorium.desktop_entry local-runtime install
python -m scriptorium.desktop_entry local-runtime ensure
python -m scriptorium.desktop_entry local-runtime status
python -m scriptorium.desktop_entry local-runtime stop
```

`install` 使用固定的 PostgreSQL 17.6 和 Elasticsearch 8.19.3 官方压缩包，逐个验证 SHA-256。无 Docker 或全局 Python/Java 前提（上述 Python 命令是源码开发用法，安装包使用内置后端）。默认当前用户登录启动，关闭研究窗口后后台保留；`stop` 明确停止本产品管理的进程。测试可用 `--no-autostart --cache tmp/research-services`，不能把测试缓存作为未校验的依赖来源。

数据库、搜索和 API 只监听回环，独立凭证保存在 Windows Credential Manager。`installation.json` 与 `runtime.json` 只记录路径、端口、状态和进程身份。前端通过 IPC 获取实际 API 端口与认证，不依赖固定 8000 或 8010。不要手动把 `connection` 命令输出写入日志或报告，该命令专供可信桌面 IPC 捕获凭证。

本机模式可在统一设置中保存任意受支持服务商的密钥到系统凭据存储；API 不回显密钥，Worker 后续调用读取最新值。服务器模式可改用 `DASHSCOPE_API_KEY`／`DEEPSEEK_API_KEY` 等环境变量，也可以在模型设置里直接保存（此时以保存值为准）。历史桌面设置的密钥不会因安装自动迁入或外发，请在新本机模式明确配置。

后台对 API/Worker 最多退避重启三次；数据库或搜索退出会停止本产品的其他子进程，记录 failed 状态。日志位于根目录 logs/。恢复时先检查 status 与日志，再执行 ensure，不按端口强杀其他程序。依赖失败、认证缺失及散列不一致均保留数据并报错。

`prepare-upgrade` 先停止自有后台，再把数据库集群、对象和安装清单一起保存到 backups/upgrade-*/。打包模式同时保留旧后端。原生停机备份不是跨用户逻辑交换格式，恢复时需匹配程序、依赖与原系统凭证；通用逻辑备份仍用 research cli backup/restore。卸载默认不删除研究目录和凭证。

发布构建使用 `scripts/build-desktop.ps1`：先前端，再打包后端，最后构建当前用户 NSIS；MSI 不宣称具有相同自动部署能力。全新用户安装、登录恢复、安装中断、升级回退须按最终验收文档补测。

## 10. 调用账本、事件和文稿

- 新增 Alembic `research_0004`，不改历史修订：调用、待核验草稿、会话事件、文稿章节。
- 模型返回用量先独立提交，再解析产物；失败不能把已耗用量归零。超时未知保留预留。查看项目 `/model-calls`，检查未知项后决定重试。
- 引文位置失败时，只接受唯一精确匹配或明确上下文消歧。最多一次模型修正，仍不合法时保存待核验草稿。引用核验可逐项绑定并持久保存，全部通过后恢复原步骤；放弃解释不会提交原来的结论。
- 会话 snapshot 与事件游标保持一致；SSE 支持 after 游标续传，客户端去重。快照包含活跃任务的文本草稿。撤回时清空敏感事件内容并保留序号，避免客户端游标倒退。
- 文稿以 editor_json 为源，引用节点必须属于当前项目且材料可用。Markdown 由服务端重建。章节 PUT 使用修订号，旧稿保留；项目 JSON/Markdown 导出包含章节。
- 请求类型用 `python scripts/generate-api-types.py` 重建，`--check` 检查漂移。浏览器业务状态用 TanStack Query 缓存；Zustand 保存界面偏好。
