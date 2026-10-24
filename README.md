# Hermeneut-Agent

**对抗性多视角话语分析工具** — 形式化记号驱动的多理论视角辩证分析，产出可追溯的证据化主体结构画像。

> v3.1 · Python 3.12+ · 356 tests · MIT

两条并行的产品线：

- **核心分析引擎（v3.1）** — SQLite 运行时，CLI + Web UI + 桌面应用 + ACP/MCP，见下文。
- **Research 服务（v4.0-dev）** — 独立的人文研究工作区，PostgreSQL + Elasticsearch 后端、版本化材料与证据锚点、`/api/v2` 接口，可选部署。见 [Research 服务](#research-服务v40-dev) 与 [`docs/research-service.md`](docs/research-service.md)。

> TopoStyle 语料特征提取工作台（TF-IDF / 持久同调 / 共现图）作为独立子项目位于 [`tools/topostyle-workbench`](tools/topostyle-workbench/README.md)，保留自有 CLI、测试与数据；产品内的 TopoStyle Persona 模块位于 `hermeneut/topostyle/`。

---

## 这是什么

Hermeneut 把聊天、访谈、写作样本等研究材料转化为**有证据追溯的主体结构分析**。每个结构候选都必须引用原文证据 span，默认状态为 `candidate`，只有人工审核通过后才进入后续流程。

核心架构是**形式化记号驱动的对抗性多视角分析**：拉康与德勒兹各有独立的形式化记号体系（mathemes / 装配代数），用紧凑的符号表示替代自然语言概念解释，在压缩 token 消耗的同时减少语义漂移。同时内置 PageIndex 文档系统，支持长篇精神分析文本的导入、检索和引文验证。

这不是临床诊断工具，也不把语言口癖直接等同于人格。

### v3.1 新特性

- **开机动画** — 黑幕品牌标识 → 过曝洗白 → 暖白技术档案底板 → 五步交互式授权 → 环形准星 → 色散故障揭幕（系统字体，零网络依赖）
- **任务系统** — 多任务对话隔离，每个任务独立消息历史，支持新建/切换/删除
- **垂直图标导航** — 左侧图标列（任务/视角/文档/检索/访谈/设置），点击展开对应面板
- **TopoStyle Persona** — 基于本地 Ollama 的拓扑人格建模，支持训练和对话
- **技术档案 UI** — 暖白底板 (#e5e3df)、橙色强调 (#ff7500)、等宽字体、发丝边框

---

## 核心能力

| | |
|---|---|
| **形式化记号系统** | 拉康 mathemes ($, a, S₁, D_m) + 德勒兹装配代数 (Ag, Dt, BwO)，全阶段 token 压缩 38-69% |
| **对抗性辩证分析** | 多视角独立分析 → 交叉批评 → 综合，内置拉康 vs 德勒兹 |
| **多源材料导入** | 聊天、访谈、写作样本统一导入，支持 UTF-8 / GB18030 / 微信格式 |
| **证据追溯** | `MaterialSource` → `EvidenceSpan` → `StructuralCandidate`，全链路来源 checksum |
| **可扩展视角** | 放置 JSON 配置到 `perspectives/` 即可自动注册（福柯、德里达等） |
| **PageIndex 文档系统** | 内容寻址存储 (SHA-256)、FTS5 全文检索、层级大纲检测、引文验证 |
| **多格式文档提取** | PageIndex 文档系统支持 txt / md / pdf / html / epub / docx / xlsx / pptx（分析材料导入限 txt / md / pdf） |
| **人工审核门禁** | CLI + JSON 审核文件驱动，所有结构候选必须人工批准 |
| **同意管理** | 细粒度同意 scope、过期、撤回与派生数据清理 |
| **Web UI** | Vite + React + TypeScript 对话式界面：任务系统、垂直图标导航、聊天分析、辩证分析、访谈、文件上传（txt/md/pdf） |
| **TopoStyle Persona** | 基于本地 Ollama 的拓扑人格建模，训练 + SSE 流式对话，复用项目/参与者/授权体系 |
| **对话模式** | 专门化话语分析 Agent，支持拉康/德勒兹理论框架的连贯对话 |
| **SSE 流式输出** | 实时流式显示分析阶段、观察、假设、反例和报告 |

---

## 形式化记号系统

v2.1 的核心创新。Agent 内部交流使用数学/拓扑形式表示替代自然语言概念解释，压缩 context 长度、减少语义漂移。

### 拉康记号

```
主体:  $ = 分裂主体    a = objet petit a    A = 大他者
能指:  S₁ = 主人能指   S₂ = 知识            S = 能指
运算:  ◇ = 幻想($◇a)  / = 压抑             → = 转喻    ∩ = 隐喻
享乐:  J = 享乐        JΦ = 阳具享乐        j = 剩余享乐

四话语代数:
  Dm [S₁→S₂/$→a]   主人话语 — 权威/命令
  Du [S₂→a/S₁→$]   大学话语 — 中立/知识
  Dh [$→S₁/a→S₂]   歇斯底里话语 — 质疑/症状
  Da [a→$/S₂→S₁]   分析者话语 — 沉默/脱落

注册: S=象征界  I=想象界  R=实在界
```

### 德勒兹记号

```
核心:  Ag = 装配    Rz = 根茎    Dm = 欲望机器    BwO = 无器官身体
运动:  Dt = 去领土化  Rt = 再领土化  Lf = 逃逸线  Bec = 生成
本体:  Mul = 多元体   Aff = 情动    Int = 强度     V↔A = 虚拟↔实际
尺度:  Mol = 大尺度(刚性)    mo = 分子(流动)

运算:  × = 异质连接   ↗ = 去领土化方向   ↘ = 再领土化方向   ∅ = 解体化   ≡ = 编码
注册:  M = 机器连接   D = 去领土化运动   B = 生成过程   I = 强度/情动
```

### Token 压缩效果

| 阶段 | 原版 | 形式化 | 压缩 |
|------|-----:|-------:|-----:|
| evidence (Lacan) | 667t | 211t | **↓68%** |
| interpreter (Lacan) | 746t | 312t | **↓58%** |
| critic (Lacan) | 477t | 238t | **↓50%** |
| cross-critique | 291t | 150t | **↓49%** |
| synthesis | 407t | 191t | **↓53%** |
| profile inference | 258t | 140t | **↓46%** |
| structural | 282t | 172t | **↓39%** |

---

## 安装

```bash
# uv（推荐）
uv venv && uv pip install -e ".[dev]"

# pip
pip install -e ".[dev]"
```

---

## 快速开始

### 证据分析流程

```bash
hermeneut init --project demo
hermeneut add-participant --project demo --id A --consent consent.json
hermeneut add-source --project demo --participant A --file story.txt
hermeneut analyze --project demo --participant A --source story.txt --mock
hermeneut review --run <run_id> --decision approve
hermeneut export --run <run_id> --pretty
```

### 对抗性多视角分析

```bash
# 列出可用视角
hermeneut perspectives

# 拉康 vs 德勒兹对抗分析
hermeneut dialectical-analyze \
  --perspectives lacan,deleuze \
  --participant A --project demo --source story.txt --mock

# 含综合报告
hermeneut dialectical-analyze \
  --perspectives lacan,deleuze \
  --participant A --project demo --source story.txt --mock --report
```

### 文档系统

```bash
hermeneut doc-ingest --path book.pdf --project demo
hermeneut doc-search --query "objet petit a" --project demo
hermeneut doc-outline --doc-id <doc_id>
hermeneut doc-verify --doc-id <doc_id> --quote "欲望是他者的欲望" --page 47
```

### 交互式界面

```powershell
.\start.ps1
```

---

## 对抗性多视角分析

多个理论视角对同一文本独立分析后交叉批评，暴露各自盲区，产出比单一视角更稳健的结果。

### 哲学对抗轴

| 维度 | 拉康 | 德勒兹 |
|------|------|--------|
| **本体论** | 匮乏/缺失驱动主体 | 充盈/生产驱动机器 |
| **语言** | 能指链优先，无意识像语言一样结构 | 语用学优先，语言是欲望机器的装配 |
| **结构** | 三角结构（想象/象征/实在） | 多元体/根茎（去中心化网络） |
| **欲望** | 欲望 = 对他者的欲望 | 欲望 = 生产性机器 |
| **重复** | 强迫性重复，回返被压抑者 | 差异的重复，每次都是新的生产 |
| **方法** | 解读症状背后的能指逻辑 | 绘制装配的连接与断裂 |

### 四阶段辩证管线

```
Phase 1  独立分析    每个视角用形式化记号独立跑 observe + interpret
Phase 2  交叉批评    N 个视角 round-robin 配对（i 批评 i+1）
Phase 3  综合        接收全部 Phase 1+2 结果，产出综合报告
Phase 4  报告        可选：生成自然语言综合报告
```

### 扩展新视角

在 `hermeneut/perspectives/` 放置 JSON 配置文件即可自动发现：

```json
{
  "id": "foucault",
  "name": "Foucauldian Power/Knowledge",
  "concept_inventory": ["power_knowledge", "disciplinary_power", "governmentality", "biopower"],
  "blind_spots": ["tends to reduce subjective experience to power effects"],
  "vocabulary": {
    "dispositif": "异质元素的异质集合——话语、制度、建筑、命题构成的网络"
  },
  "evidence_prompt_variant": null,
  "interpreter_prompt_variant": null,
  "critique_prompt_variant": null
}
```

---

## 文档系统

移植自 MISAKA-Agent 的 PageIndex 文档系统，支持长篇精神分析文本的处理与引文验证。

| 组件 | 说明 |
|------|------|
| **内容寻址** | SHA-256 前 12 位作为 doc_id，相同文档自动去重 |
| **页级存储** | 每页文本独立存储，支持页级导航和检索 |
| **FTS5 全文索引** | SQLite FTS5 虚拟表，支持中文分词检索 |
| **大纲检测** | 自动识别 CHAPTER / BOOK / SECTION 层级（英/法/德/西/意多语言） |
| **引文归一化** | NFKC Unicode 归一化 + 连字符/软连字符/空白折叠，跨版本 OCR 匹配 |

---

## API

### TopoStyle 本地 Persona

TopoStyle 复用 Hermeneut 的项目、参与者、授权和 SQLite 存储。模型通过本地 Ollama 运行，默认使用 `qwen2.5:3b` 和 `nomic-embed-text`：

```bash
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
uv pip install -e ".[dev]"
```

创建项目和参与者后，可调用 `POST /api/v1/personas` 创建 Persona，调用
`POST /api/v1/personas/{id}/train` 生成拓扑与人格 artifact，再调用
`POST /api/v1/personas/{id}/chat` 获取 SSE 流式回复。所有回复带有 `ai_generated: true`；撤回参与者授权会删除 Persona 的派生数据与对话。

### 启动

```bash
uvicorn hermeneut.api:app --host 127.0.0.1 --port 8000
```

默认仅绑定本机地址。设置 `LACAN_API_KEY` 环境变量启用 Bearer Token 认证；不设置时无需认证。
未配置 `DASHSCOPE_API_KEY` 时，Web API 会自动使用本地 `FakeProvider`，可直接运行分析和辩证分析演示；配置后才调用 Qwen。

### 端点

| 方法 | 端点 | 描述 |
|------|------|------|
| `GET` | `/api/v1/projects` | 列出所有项目 |
| `POST` | `/api/v1/projects` | 创建项目 |
| `GET` | `/api/v1/projects/{id}` | 查询项目详情 |
| `DELETE` | `/api/v1/projects/{id}` | 删除项目（级联清理） |
| `GET` | `/api/v1/projects/{id}/participants` | 列出项目参与者 |
| `DELETE` | `/api/v1/projects/{id}/participants/{pid}` | 删除参与者 |
| `POST` | `/api/v1/participants` | 添加参与者 |
| `POST` | `/api/v1/participants/{pid}/sources` | 上传材料 |
| `POST` | `/api/v1/analysis-runs` | 运行分析 |
| `GET` | `/api/v1/analysis-runs/{rid}` | 查询运行状态 |
| `POST` | `/api/v1/analysis-runs/{rid}/reviews` | 提交审核 |
| `GET` | `/api/v1/analysis-runs/{rid}/packet` | 导出审核包 |
| `GET` | `/api/v1/analysis-runs/{rid}/graph` | 导出图谱 |
| `POST` | `/api/v1/participants/{pid}/withdraw` | 撤回参与者 |
| `POST` | `/api/v1/dialectical/run` | 运行多视角辩证分析 |
| `GET` | `/api/v1/perspectives` | 列出可用理论视角 |
| `POST` | `/api/v1/interviews` | 创建交互式访谈会话 |
| `GET` | `/api/v1/interviews/{session_id}` | 查询访谈状态和当前问题 |
| `POST` | `/api/v1/interviews/{session_id}/turns` | 提交访谈回答并推进问题 |
| `POST` | `/api/v1/interviews/{session_id}/pause` | 暂停访谈 |
| `POST` | `/api/v1/interviews/{session_id}/resume` | 恢复访谈 |
| `POST` | `/api/v1/interviews/{session_id}/complete` | 导出 interview JSON 并启动分析 |
| `POST` | `/api/v1/interviews/{session_id}/withdraw` | 撤回访谈会话 |
| `POST` | `/api/v1/interviews/{session_id}/reset` | 清零并创建新的访谈会话 |
| `POST` | `/api/v1/personas` | 创建 TopoStyle Persona |
| `POST` | `/api/v1/personas/{id}/train` | 训练 Persona 拓扑与人格 |
| `POST` | `/api/v1/personas/{id}/chat` | Persona 对话（SSE 流式） |
| `GET` | `/api/v1/health` | 健康检查 |

### 示例

```bash
# 创建项目
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"id": "demo", "owner_id": "researcher"}'

# 上传材料
curl -X POST "http://localhost:8000/api/v1/participants/A/sources" \
  -F "project_id=demo" -F "file=@story.txt"

# 运行辩证分析
curl -X POST http://localhost:8000/api/v1/dialectical/run \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "demo",
    "participant_id": "A",
    "source_ids": ["source_1"],
    "perspective_ids": ["lacan", "deleuze"],
    "idempotency_key": "dial_001",
    "generate_report": true
  }'
```

## Web UI

浏览器访问 `http://127.0.0.1:8000` 即可使用图形界面（启动方式同上 `uvicorn hermeneut.api:app`）。

Windows 下也可以在项目根目录执行 `.\start-webui.ps1` 启动服务。

### 技术栈

- **前端**: Vite 8 + React 19 + TypeScript + Tailwind CSS 4 + Zustand
- **后端**: FastAPI + SSE (Server-Sent Events)
- **流式输出**: 原生 fetch + ReadableStream

### 开发模式

```bash
# Terminal 1: 后端
uvicorn hermeneut.api:app --reload --port 8000

# Terminal 2: 前端
cd web && npm run dev  # → http://localhost:5173
```

### 生产构建

```bash
cd web && npm run build
uvicorn hermeneut.api:app --port 8000  # 访问 http://127.0.0.1:8000
```

### 功能

- **任务系统**：多任务对话隔离，每个任务独立消息历史，支持新建/切换/删除/自动命名
- **垂直图标导航**：左侧图标列（任务/视角/文档/检索/访谈/设置），点击展开对应面板，抽屉式抽拉
- **开机动画**：品牌标识揭幕动画，系统字体零网络依赖
- **对话模式**：与专门化话语分析 Agent 进行连贯对话，支持拉康/德勒兹理论框架
- **分析模式**：输入文本或上传文件（`.txt / .md / .pdf`），流式显示 Observation / Hypothesis / Counterexample 卡片
- **辩证分析**：一键运行四阶段对抗性辩证管线（Lacan × Deleuze），实时显示进度
- **TopoStyle Persona**：基于本地 Ollama 的拓扑人格建模，训练 + 对话
- **视角面板**：查看已注册视角的概念清单与盲点
- **文档上传**：拖拽上传到 PageIndex 文档系统
- **语料检索**：搜索已索引的理论文档
- **交互式访谈**：固定主问题结合受限动态追问，支持暂停、恢复、完成和撤回

### 模式切换

| 模式 | 说明 |
|------|------|
| 对话 | 与话语分析 Agent 进行连贯对话，适合探索性讨论 |
| 分析 | 单视角证据分析，流式输出观察/假设/反例 |
| 辩证 | 多视角对抗性分析，四阶段管线（独立分析→交叉批判→综合→报告） |
| 访谈 | 结构化访谈，支持暂停/恢复/完成/撤回 |

### API Key

如果服务端设置了 `LACAN_API_KEY`，点击底栏 `KEY` 输入 API Key（存储在浏览器 localStorage）。未设置时无需配置。

---

## 桌面应用

Hermeneut 提供基于 Tauri v2 的桌面应用，打包为独立 Windows 安装程序，无需手动安装 Python 或 Node.js。

### 架构

```
Tauri Application
├── WebView (React SPA)        ← 前端界面
├── Rust Main Binary           ← Sidecar 进程管理、API Key 存储
└── Sidecar (PyInstaller exe)  ← Python FastAPI 后端，自动启动
```

数据存储在 `%APPDATA%\app.hermeneut.desktop\`（数据库 + 上传文件）。

### 开发模式

```powershell
# 终端 1: 后端（开发时手动启动）
uvicorn hermeneut.api:app --host 127.0.0.1 --port 8000

# 终端 2: Tauri 开发
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
cargo tauri dev
```

### 构建安装程序

**前置条件**：
- Rust stable + VS Build Tools 2022
- `cargo install tauri-cli --version "^2"`
- `pip install pyinstaller`

```powershell
# 一键构建
.\scripts\build-desktop.ps1

# 或分步构建
.\scripts\build-sidecar.ps1       # PyInstaller → src-tauri/bin/
cd web && npm ci && npm run build:tauri
cargo tauri build                  # → src-tauri/target/release/bundle/nsis/
```

输出：`Hermeneut-Agent_3.1.0_x64-setup.exe`（NSIS 安装程序）

### 清理构建产物

```powershell
.\scripts\clean.ps1
```

---

## ACP（Agent Client Protocol）

Hermeneut 支持通过 ACP 协议在 Zed 等编辑器中直接调用，选中文字即可分析。

### 启动

```bash
hermeneut-acp --mock          # 无需 API key（mock 模式）
hermeneut-acp                 # 需要 DASHSCOPE_API_KEY
python -m hermeneut.acp --mock
```

### Zed 配置

在 Zed `settings.json` 中添加：

```json
{
  "agent_servers": {
    "hermeneut": {
      "type": "custom",
      "command": "python",
      "args": ["-m", "hermeneut.acp", "--mock"]
    }
  }
}
```

### 支持的操作

| 输入示例 | 操作 |
|----------|------|
| "列出可用视角" / "perspectives" | 列出已注册的理论视角 |
| "分析以下文本：..." | 单视角证据分析 |
| "辩证分析：..." | 拉康 vs 德勒兹对抗性分析 |
| "搜索：能指" | 文档全文检索 |

### MCP（Model Context Protocol）

Hermeneut 也可作为 MCP 服务器运行，供 Qoder、Claude Desktop 等 MCP 客户端直接调用。

```bash
hermeneut-mcp --mock          # 无需 API key
hermeneut-mcp                 # 需要 DASHSCOPE_API_KEY
python -m hermeneut.mcp_server --mock
```

暴露 4 个 MCP 工具：

| 工具 | 说明 |
|------|------|
| `hermeneut_analyze` | 单视角证据分析 |
| `hermeneut_dialectical` | 多视角辩证分析（拉康 vs 德勒兹） |
| `hermeneut_perspectives` | 列出可用理论视角 |
| `hermeneut_search` | 文档全文检索 |

MCP 客户端配置示例（Qoder / Claude Desktop）：

```json
{
  "mcpServers": {
    "hermeneut": {
      "command": "python",
      "args": ["-m", "hermeneut.mcp_server", "--mock"]
    }
  }
}
```

---

## Research 服务（v4.0-dev）

面向长期人文研究的独立服务，与核心引擎的 SQLite 运行时完全隔离，采用 PostgreSQL 持久化 + Elasticsearch 检索，提供版本化材料、证据锚点、方法运行、决策留痕与统一研究工作区。默认为可选部署，不影响核心分析引擎的使用。

### 能力

| | |
|---|---|
| **版本化材料** | 导入 → 分段 (segments) → TEI → OCR → 修订 (revisions) 全链路版本管理 |
| **证据锚点** | `anchors` 将结论绑定到材料精确位置，支持 `verify-anchors` 校验 |
| **方法与作业** | `method-runs` / `jobs` / `research-runs` 记录研究过程，Worker 异步执行、可中断恢复 |
| **对话与决策** | `conversations` / `messages` / `decisions` 留痕，`citation-drafts` 管理引文草稿 |
| **对象存储** | 可选 S3 后端（`HERMENEUT_OBJECT_BACKEND=s3`），兼容 SeaweedFS |
| **OCR** | rapidocr / tesseract 双后端，支持扫描版文献 |
| **统一工作台** | Web 端 Research Workbench + Unified Workspace（`web/src/features/`） |
| **平滑迁移** | `migrate-sqlite` 从核心引擎的 SQLite 快照迁移，Alembic 版本化 schema |

### 接口

API 前缀 `/api/v2/projects/{project_id}/...`（materials、anchors、records、method-runs、jobs、conversations、research-runs、decisions、participants、personas、citation-drafts 等），并提供 `/api/v1` 兼容层与 `/health`、`/api/v2/system/*`。

### 启动

```bash
# 安装 research extra
uv pip install -e ".[research]"

# 单机开发（本地 PostgreSQL + Elasticsearch）
hermeneut-research init-db
hermeneut-research serve          # 默认 127.0.0.1:8010
hermeneut-research worker         # 异步作业 Worker

# 或一键脚本（Windows）
.\scripts\start-research.ps1

# 容器编排（postgres + elasticsearch + migrate/api/worker）
docker compose -f compose.research.yml up
```

配置项见 [`.env.research.example`](.env.research.example)。运维、迁移与恢复流程详见 [`docs/research-service.md`](docs/research-service.md)；架构决策见 [`docs/adr/`](docs/adr/)。

### 验收与质量

```powershell
.\scripts\run-acceptance.ps1      # 可复现验收（工作区摘要 + 逐项日志）
.\scripts\test-services.ps1       # 本地临时 PG + ES
```

验收报告位于 `docs/acceptance/`，学术质量案例（Q-01~Q-08）由 `scripts/quality-cases.py` 生成。

---

## 隐私与伦理

| 原则 | 说明 |
|------|------|
| **默认关闭** | 画像和生成授权默认关闭，必须显式同意 |
| **细粒度控制** | `profile_analysis` / `agent_simulation` / `story_generation` / `public_export` 分开控制 |
| **原文保护** | 原始文本不写入 ProfileArtifact 的观察层和生成提示 |
| **撤回清理** | 撤回时清理原始材料、EvidenceSpan、结构候选、画像、审核文件和派生导出 |
| **本地存储** | 数据库和上传材料默认不提交到 GitHub |

---

## 开发

```bash
pytest tests/ -q          # 运行全部测试 (356)
ruff check hermeneut/     # 代码检查
```

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| 数据验证 | Pydantic v2 |
| 数据库 | SQLite + FTS5 |
| Web 框架 | FastAPI + Uvicorn |
| 前端框架 | Vite 8 + React 19 + TypeScript + Tailwind CSS 4 |
| 状态管理 | Zustand |
| 桌面应用 | Tauri v2 + PyInstaller sidecar |
| LLM | DashScope (通义千问) OpenAI-compatible API |
| 流式输出 | SSE (Server-Sent Events) |
| 形式化记号 | `hermeneut/formal/` — mathemes + discourse algebra + register taxonomy |
| 文档提取 | pypdf / HTMLParser / zipfile |
| 测试 | pytest + pytest-asyncio |

---

## 多源主体结构画像

除单源证据分析外，Hermeneut 支持跨来源互证的主体结构画像构建：

```json
{
  "sources": [
    { "source_id": "chat_a", "participant_id": "A", "source_type": "chat", "path": "chat.txt" },
    { "source_id": "interview_a", "participant_id": "A", "source_type": "interview", "path": "interview.json" },
    { "source_id": "writing_a", "participant_id": "A", "source_type": "writing", "path": "continuation.txt" }
  ]
}
```

### 访谈 JSON 格式

`source_type: "interview"` 对应的文件为 JSON 格式，结构如下：

```json
{
  "turns": [
    { "question": "你第一次感到焦虑是什么时候？", "answer_text": "大概初中的时候…" },
    { "question": "当时发生了什么？", "answer_text": "有一次考试…" }
  ]
}
```

每个 turn 必须包含 `question`（问题文本）和回答字段。回答字段按优先级尝试 `answer_text` → `answer` → `text`，三者取其一即可。字段缺失或为空时该 turn 会被跳过（除非提供了 `answer_span_ids` 指向已有证据 span）。

```bash
hermeneut subject build --participant A --sources sources.json --mode full \
  --batch-size 80 --with-relations --cards-dir data/subject-artifacts
hermeneut subject show --participant A --cards-dir data/subject-artifacts
hermeneut subject review --participant A --input review.json --cards-dir data/subject-artifacts
hermeneut subject export --participant A --cards-dir data/subject-artifacts --to subject.json
```

主体分析按重叠窗口覆盖全部消息。关系层先生成有向互动事件，再由 Qwen 复核关系候选。所有候选保留 span、时间和场景证据。可用 `--aliases aliases.json` 提供人工确认的参与者别名表。

Qwen 结构抽取需要设置 `DASHSCOPE_API_KEY` 环境变量。Qwen 失败时仍会生成观察层画像。

---

## 致谢

Hermeneut-Agent 的文档系统（`hermeneut/documents/`）移植自 [MISAKA-Agent](https://github.com/Luciole-Studio/Misaka-Agent)（Copyright 2026 Luciole Studio, [Apache License 2.0](LICENSE-MISAKA)），包括内容寻址存储、层级大纲检测、引文归一化验证和多格式文本提取器。对抗性多视角辩证分析的架构设计亦受 MISAKA 多智能体编排的启发。详见 [NOTICE](NOTICE)。

---

MIT License
