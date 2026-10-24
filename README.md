# Scriptorium

**人文研究 Agent** — 面向人文学科的证据锚定、多视角批判性解读工作台：把版本化原文、理论文本、访谈与文稿，转化为可回溯到原文精确位置、可核验引文的研究论证。

> v3.1.1 · Python 3.12+ · 312 tests · MIT · 本地优先（默认仅绑定 127.0.0.1）

Scriptorium（缮写室）把「细读 → 批判性解读 → 论证构建」放进同一条证据链：每个结论都能回跳到原文的 code point 级锚点，每条引文都必须通过核验，每个结构性主张默认都是 `candidate`，只有人工审核通过才进入论证。它不做临床诊断，也不把语言口癖等同于人格——它做的是**把解读锚定到证据**。

---

## 两种运行时，同一个 agent

| 运行时 | 定位 | 后端 | 入口 |
|---|---|---|---|
| **研究工作台**（推荐） | 完整人文研究：版本化材料、证据锚点、批判方法、引文核验、统一工作台（图形界面） | PostgreSQL + Elasticsearch | `scriptorium research serve` → Web `http://127.0.0.1:8010` |
| **本地单机** | 轻量证据分析与对抗性辩证，无需外部服务，开箱即用（CLI / 终端 / 编辑器插件） | SQLite | `scriptorium <命令>` · `scriptorium interactive` · `scriptorium-acp` · `scriptorium-mcp` |

图形研究工作台由研究服务提供；本地单机运行时保留全部单机分析能力（证据分析、对抗性辩证、文档系统、主体画像、访谈、风格模拟），以 CLI、交互式终端和 ACP/MCP 编辑器插件的形式使用，并通过统一的 `scriptorium research …` 子命令接入研究服务。两者共享同一套项目／参与者／授权与证据模型。

> TopoStyle 语料特征提取工作台（TF-IDF / 持久同调 / 共现图）作为独立子项目位于 [`tools/topostyle-workbench`](tools/topostyle-workbench/README.md)，保留自有 CLI、测试与数据；产品内的 TopoStyle 风格模拟模块位于 `scriptorium/topostyle/`。

---

## 批判方法

Scriptorium 的解读能力组织为可单独或组合调用的**方法**，全部产出带证据锚点的结构化记录，而非自由文本断言：

| 方法 | 界面标签 | 说明 |
|---|---|---|
| **思想构境** `situating.v1` | 构境 | 六维档案、概念记录、跨材料选择、竞争档案比较与人工修订 |
| **内在批判** `immanent_critique.v1` | 内在批判 | 立场、尺度、困难、转化候选、关系列表与依据；无依据的转化会被拒绝 |
| **视差分析** `parallax.v1` | 视差 | 位置、对象显现、位移、已排除原因、反驳条件与裂隙候选 |
| **理论视角比较** | 理论视角比较 | 多理论视角对同一文本独立解读 → 交叉批评 → 综合，内置**拉康 × 德勒兹**对抗性辩证分析 |
| **主体分析** | 主体分析 | 跨来源互证的多源主体结构画像（聊天／访谈／写作样本） |
| **风格模拟** | 风格模拟 | TopoStyle 本地 Ollama 拓扑人格建模，训练 + SSE 流式对话 |

其中「理论视角比较」源自 Scriptorium 最早的核心创新——**形式化记号驱动的对抗性多视角分析**：拉康与德勒兹各有独立的形式化记号体系（mathemes / 装配代数），用紧凑符号替代自然语言概念解释，压缩 token 的同时减少语义漂移。详见 [形式化记号系统](#形式化记号系统) 与 [对抗性多视角分析](#对抗性多视角分析)。

---

## 研究闭环：材料 → 证据 → 解读 → 论证

研究工作台把研究材料转化为**有证据追溯的解读与论证**：

- **版本化材料** — 原件／理论文本以不可变版本链导入（TXT / MD / PDF / TEI，扫描版走 OCR），修订产生新版本，旧证据永远指向旧版本。
- **证据锚点** — 选中文字即成为 code point 级锚点，结论、笔记、引文都绑定到锚点，可一键回跳原文。
- **方法化解读** — 上表六种方法产出结构化记录（构境档案、转化候选、视差裂隙、辩证综合……），每条都带依据。
- **引文核验** — 引文草稿必须绑定到已核验的原文摘录才算通过，未核验的引文不进入文稿。
- **人工审核门禁** — 结构性主张默认 `candidate`，人工批准后才进入论证与文稿；撤回参与者授权会级联清理其派生数据。
- **文稿与导出** — Tiptap JSON 编辑源 + 引用/脚注节点，章节独立修订、自动保存与冲突保留；AI「建议修改」只产生候选，接受后才写入正式稿；Pandoc 导出 DOCX / Markdown / HTML（内置中英文 CSL）。
- **团队治理** — OIDC（Keycloak）登录、负责人/研究者/评议者/只读四级角色、外部模型外发预算与敏感材料限制、模型调用审计账本。

同时内置 PageIndex 文档系统，支持长篇理论文本的导入、检索和引文验证。

---

## 平台能力

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
| **集成工作台** | 项目/会话导航 + 研究对话 + 文档区三位一体：专注阅读、文档标签、命令面板（Ctrl+K）、响应式至 480px、安静模式与减少动态效果 |
| **统一研究工作台** | Vite + React + TypeScript：材料库 / 阅读区 / 笔记编辑三区布局，方法化解读、证据锚点回跳、引文核验 |
| **文稿写作** | Tiptap JSON 编辑源、引用与脚注节点、章节修订与历史版本比较恢复、AI 建议修改（接受前不入正文） |
| **导出** | 固定 Pandoc 3.12.1（官方散列校验）+ 内置 CSL：DOCX / Markdown / HTML；保留 JSON / TEI 档案导出 |
| **团队与治理** | OIDC code + PKCE 登录（Keycloak）、四级项目角色、外发政策与累计预算、调用账本与审计；服务器不保存 OIDC token |
| **TopoStyle 风格模拟** | 基于本地 Ollama 的拓扑人格建模，训练 + SSE 流式对话，复用项目/参与者/授权体系 |
| **研究对话** | 专门化话语分析 Agent，围绕所选材料进行连贯的批判性对话 |
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

### 研究工作台（推荐）

```bash
uv pip install -e ".[research,dev]"   # 安装研究服务依赖
# 准备可连接的 PostgreSQL 17 与 Elasticsearch 8.19（或用 compose.research.yml）
scriptorium research init-db
scriptorium research serve            # → http://127.0.0.1:8010
scriptorium research worker           # 另开一个终端
```

浏览器打开 `http://127.0.0.1:8010`，新建项目 → 导入材料 → 选中原文保存证据锚点 → 选择方法（构境 / 内在批判 / 视差 / 理论视角比较）运行 → 核验引文 → 导出文稿。

以下命令属于**本地单机运行时**（SQLite，无需外部服务），适合快速证据分析与对抗性辩证。

### 证据分析流程

```bash
scriptorium init --project demo
scriptorium add-participant --project demo --id A --consent consent.json
scriptorium add-source --project demo --participant A --file story.txt
scriptorium analyze --project demo --participant A --source story.txt --mock
scriptorium review --run <run_id> --decision approve
scriptorium export --run <run_id> --pretty
```

### 对抗性多视角分析

```bash
# 列出可用视角
scriptorium perspectives

# 拉康 vs 德勒兹对抗分析
scriptorium dialectical-analyze \
  --perspectives lacan,deleuze \
  --participant A --project demo --source story.txt --mock

# 含综合报告
scriptorium dialectical-analyze \
  --perspectives lacan,deleuze \
  --participant A --project demo --source story.txt --mock --report
```

### 文档系统

```bash
scriptorium doc-ingest --path book.pdf --project demo
scriptorium doc-search --query "objet petit a" --project demo
scriptorium doc-outline --doc-id <doc_id>
scriptorium doc-verify --doc-id <doc_id> --quote "欲望是他者的欲望" --page 47
```

### 交互式终端

```powershell
.\start.ps1          # 等价于 scriptorium interactive，引导式终端分析
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

在 `scriptorium/perspectives/` 放置 JSON 配置文件即可自动发现：

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

## API（本地单机 · `/api/v1`）

本地单机运行时（SQLite）暴露 `/api/v1` 接口，供 CLI、ACP、MCP 与本地分析使用，由 `uvicorn scriptorium.api:app`（默认 `127.0.0.1:8000`）提供。图形研究工作台走研究服务的 `/api/v2`（见 [研究工作台服务](#研究工作台服务)）。

### TopoStyle 本地 Persona

TopoStyle 复用 Scriptorium 的项目、参与者、授权和 SQLite 存储。模型通过本地 Ollama 运行，默认使用 `qwen2.5:3b` 和 `nomic-embed-text`：

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
uvicorn scriptorium.api:app --host 127.0.0.1 --port 8000
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

## 研究工作台（Web）

图形界面是**集成研究工作台**（`web/src/features/workspace/`），由研究服务提供：启动 `scriptorium research serve` 后浏览器访问 `http://127.0.0.1:8010`。工作台围绕「材料 → 证据 → 解读 → 论证 → 文稿」组织，取代了早期以聊天为中心的界面。设计与实现记录见 [`docs/integrated-workbench-design.md`](docs/integrated-workbench-design.md)，部署与运维见 [`docs/integrated-workbench-runbook.md`](docs/integrated-workbench-runbook.md)。

### 布局

项目导航（232px）+ 研究对话 + 文档区，文档宽度可拖动或键盘调整；聊天、并置、专注阅读是布局状态而非业务入口。1180px 以下导航进入抽屉，960px 以下对话与文档单区切换，480px 保留完整输入与文稿操作。设置与项目治理为独立弹层，命令面板 Ctrl+K；安静模式与系统减少动态效果会关闭全部转场。

- **材料库 / 项目导航**（左）— 项目、会话、材料、历史分析、研究文档树
- **对话与方法区**（中）— 研究对话流、方法调用、决定点（decision）、任务进度、引文核验卡片
- **阅读 / 编辑区**（右）— 原文阅读与选词锚定、版本对照、研究笔记与文稿编辑、书目与处理状态

### 直接提问

对话框默认就是**提问**：不必先勾材料或选方法。输入问题后，服务会检索本项目材料、锁定阅读窗口，只依据这些材料作答，并把每条引文对齐成原文锚点；回答记录同时保留检索方式（`search` / `material_scan` / `explicit`）、覆盖范围、未决问题与追问建议。回答卡片上的**深入完整研究**会把同一冻结范围交给完整方法流水线。未选择材料时自动检索；选中材料或选区则只读所选范围；真实模式缺少模型密钥会明确失败，不会退回演示。详见 [提问即研究记录](docs/acceptance/ask-first-research-20261024.md)。

### 工具与方法

底栏仍可切换更专门的**工具**与**方法**（见 [批判方法](#批判方法)）：

| 类型 | 选项 |
|---|---|
| 工具 | 提问（默认） · 研究对话 · 完整研究 · 理论视角比较 · 主体分析 · 风格模拟 |
| 方法 | 思想构境 · 内在批判 · 视差分析 |

选中原文即可保存为证据锚点，结论与引文绑定锚点后可一键回跳原文；运行模式可切换「真实模型 / 演示（不产生学术结论）」。

### 文稿、建议与导出

文稿默认进入可视化编辑：Tiptap JSON 为编辑源、Markdown 为派生文本，章节独立修订，自动保存约 1.2 秒，冲突保留本机草稿不覆盖远端，历史版本可比较并恢复为新修订。AI「建议修改」只创建候选版本，展示前后内容与理由，接受后才写入正式稿；过期修订拒绝写入。导出在后台运行固定 Pandoc（官方 URL + SHA-256 校验），支持 DOCX / Markdown / HTML 与内置中文脚注、英文脚注、作者年份 CSL；DOCX 脚注与书目来自文稿引用节点和材料书目信息，JSON / TEI 沿用项目档案导出。

### 项目与成员治理

团队部署下（见 [团队部署](#团队部署-linux)），项目负责人可在「项目与成员」面板按 `user_id` 邀请成员，角色为负责人 / 研究者 / 评议者 / 只读，最后一名负责人受保护。模型外发受政策约束：负责人指定允许的服务商主机、材料、文本版本、用途说明与累计预算，敏感材料禁止外发；全部模型调用与项目变更进入审计账本，普通成员不能修改模型地址或密钥。

### 技术栈

- **前端**: Vite 8 + React 19 + TypeScript + Tailwind CSS 4 + Zustand + TanStack Query + Radix UI + Motion + Tiptap（开源核心）
- **后端**: 研究服务 FastAPI + PostgreSQL + Elasticsearch，SSE 推送任务与对话事件
- **流式输出**: 原生 fetch + ReadableStream；任务进度经 SSE 续传

### 开发模式

```bash
# Terminal 1: 研究服务（需先起 PostgreSQL + Elasticsearch，见「研究工作台服务」）
scriptorium research serve        # → http://127.0.0.1:8010
scriptorium research worker       # 异步作业 Worker

# Terminal 2: 前端热更新
cd web && npm run dev             # → http://localhost:5173
```

前端开发服务器通过 `web/vite.config.ts` 代理 `/api` 到研究服务。生产构建 `cd web && npm run build` 后，研究服务会自动挂载 `web/dist`。

### 服务与密钥

在右侧「设置与档案」面板配置研究服务地址与密钥：远程访问必须设置 `SCRIPTORIUM_RESEARCH_API_KEY` 并走 HTTPS 反向代理；本机可免密。研究模型支持通义千问、DeepSeek、OpenAI、Moonshot、智谱 GLM、本机 Ollama 与自定义 OpenAI 兼容端点：在「研究模型」里选择服务商、填写接口地址／模型、保存密钥并测试连接；密钥存于系统凭据（或非 Windows 下的私有文件），接口不回显。也可继续用 `DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY` 等环境变量。

---

## 桌面应用

Scriptorium 提供基于 Tauri v2 的桌面应用，打包为独立 Windows 安装程序，无需手动安装 Python 或 Node.js。

### 架构

```
Tauri Application
├── WebView (React SPA)        ← 前端界面
├── Rust Main Binary           ← Sidecar 进程管理、API Key 存储
└── Sidecar (PyInstaller exe)  ← Python FastAPI 后端，自动启动
```

数据存储在 `%APPDATA%\app.scriptorium.desktop\`（数据库 + 上传文件）。

### 开发模式

```powershell
# 终端 1: 后端（开发时手动启动）
uvicorn scriptorium.api:app --host 127.0.0.1 --port 8000

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

输出：`Scriptorium_3.1.0_x64-setup.exe`（NSIS 安装程序）

### 清理构建产物

```powershell
.\scripts\clean.ps1
```

---

## ACP（Agent Client Protocol）

Scriptorium 支持通过 ACP 协议在 Zed 等编辑器中直接调用，选中文字即可分析。

### 启动

```bash
scriptorium-acp --mock          # 无需 API key（mock 模式）
scriptorium-acp                 # 需要 DASHSCOPE_API_KEY
python -m scriptorium.acp --mock
```

### Zed 配置

在 Zed `settings.json` 中添加：

```json
{
  "agent_servers": {
    "scriptorium": {
      "type": "custom",
      "command": "python",
      "args": ["-m", "scriptorium.acp", "--mock"]
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

Scriptorium 也可作为 MCP 服务器运行，供 Qoder、Claude Desktop 等 MCP 客户端直接调用。

```bash
scriptorium-mcp --mock          # 无需 API key
scriptorium-mcp                 # 需要 DASHSCOPE_API_KEY
python -m scriptorium.mcp_server --mock
```

暴露 4 个 MCP 工具：

| 工具 | 说明 |
|------|------|
| `scriptorium_analyze` | 单视角证据分析 |
| `scriptorium_dialectical` | 多视角辩证分析（拉康 vs 德勒兹） |
| `scriptorium_perspectives` | 列出可用理论视角 |
| `scriptorium_search` | 文档全文检索 |

MCP 客户端配置示例（Qoder / Claude Desktop）：

```json
{
  "mcpServers": {
    "scriptorium": {
      "command": "python",
      "args": ["-m", "scriptorium.mcp_server", "--mock"]
    }
  }
}
```

---

## 研究工作台服务

承载图形研究工作台的运行时，与本地单机的 SQLite 运行时相互隔离：采用 PostgreSQL 持久化 + Elasticsearch 检索，提供版本化材料、证据锚点、方法运行、决策留痕与统一研究工作区。这是完整体验所推荐的后端；本地单机运行时仍可独立用于 CLI / ACP / MCP 分析。

### 能力

| | |
|---|---|
| **版本化材料** | 导入 → 分段 (segments) → TEI → OCR → 修订 (revisions) 全链路版本管理 |
| **证据锚点** | `anchors` 将结论绑定到材料精确位置，支持 `verify-anchors` 校验 |
| **方法与作业** | `method-runs` / `jobs` / `research-runs` 记录研究过程，Worker 异步执行、可中断恢复 |
| **对话与决策** | `conversations` / `messages` / `decisions` 留痕，`citation-drafts` 管理引文草稿 |
| **对象存储** | 可选 S3 后端（`SCRIPTORIUM_OBJECT_BACKEND=s3`），兼容 SeaweedFS |
| **OCR** | rapidocr / tesseract 双后端，支持扫描版文献 |
| **统一工作台** | Web 端研究工作台（`web/src/features/workspace/`），服务自动挂载前端构建产物 |
| **文稿与导出** | Tiptap JSON 编辑源与章节修订、AI 建议修改、后台 Pandoc DOCX / Markdown / HTML（内置 CSL） |
| **治理与账本** | OIDC 登录、项目角色、外发政策与预算、模型调用与项目变更审计（研究 / 问答 / 访谈 / Persona 全部接入记账） |
| **平滑迁移** | `migrate-sqlite` 从本地单机的 SQLite 快照非破坏式迁移，Alembic 版本化 schema |

### 接口

API 前缀 `/api/v2/projects/{project_id}/...`（materials、anchors、records、method-runs、jobs、conversations、research-runs、decisions、participants、personas、citation-drafts 等），工作台治理接口在同前缀下的 `membership` / `members` / `policy` / `classification` / `audit` / `workspace` / `tasks` / `artifacts/{rid}`（comments、restore、change-proposals、exports），登录为 `/api/v2/auth/{session,login,callback,logout}`，并提供 `/api/v1` 兼容层与 `/health`、`/api/v2/system/*`。请求/响应模型由 OpenAPI 生成（`scripts/generate-api-types.py` → `web/src/features/workspace/api/generated.ts`）。

### 启动

```bash
# 安装 research extra
uv pip install -e ".[research]"

# 单机开发（本地 PostgreSQL + Elasticsearch）——统一入口
scriptorium research init-db
scriptorium research serve          # 默认 127.0.0.1:8010
scriptorium research worker         # 异步作业 Worker

# 等价命令
python -m scriptorium.research.cli serve
.\scripts\start-research.ps1        # Windows 一键脚本

# 容器编排（postgres + elasticsearch + migrate/api/worker）
docker compose -f compose.research.yml up
```

配置项见 [`.env.research.example`](.env.research.example)。运维、迁移与恢复流程详见 [`docs/research-service.md`](docs/research-service.md)；架构决策见 [`docs/adr/`](docs/adr/)。

### 团队部署（Linux）

课题组多人协作使用独立的 `compose.team.yml`（不要与个人 `compose.research.yml` 叠加）：PostgreSQL + Elasticsearch + Keycloak 26.4.7（OIDC，realm 导入 `deploy/team/scriptorium-realm.json`）+ Caddy 2.10.2 HTTPS 反向代理，仅发布 80/443，数据库与身份服务端口不暴露。登录采用 authorization code + PKCE，不使用客户端秘密；管理员由 `SCRIPTORIUM_ADMIN_SUBJECTS` 指定。完整步骤见 [`docs/integrated-workbench-runbook.md`](docs/integrated-workbench-runbook.md)。

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
pytest tests/ -q          # 运行全部测试 (312)
ruff check scriptorium/     # 代码检查
```

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| 数据验证 | Pydantic v2 |
| 数据库 | SQLite + FTS5（本地单机）· PostgreSQL + Elasticsearch（研究工作台） |
| Web 框架 | FastAPI + Uvicorn |
| 前端框架 | Vite 8 + React 19 + TypeScript + Tailwind CSS 4 |
| 状态管理 | Zustand |
| 桌面应用 | Tauri v2 + PyInstaller sidecar |
| LLM | DashScope (通义千问) OpenAI-compatible API |
| 流式输出 | SSE (Server-Sent Events) |
| 形式化记号 | `scriptorium/formal/` — mathemes + discourse algebra + register taxonomy |
| 文档提取 | pypdf / HTMLParser / zipfile |
| 测试 | pytest + pytest-asyncio |

---

## 多源主体结构画像

除单源证据分析外，Scriptorium 支持跨来源互证的主体结构画像构建：

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
scriptorium subject build --participant A --sources sources.json --mode full \
  --batch-size 80 --with-relations --cards-dir data/subject-artifacts
scriptorium subject show --participant A --cards-dir data/subject-artifacts
scriptorium subject review --participant A --input review.json --cards-dir data/subject-artifacts
scriptorium subject export --participant A --cards-dir data/subject-artifacts --to subject.json
```

主体分析按重叠窗口覆盖全部消息。关系层先生成有向互动事件，再由 Qwen 复核关系候选。所有候选保留 span、时间和场景证据。可用 `--aliases aliases.json` 提供人工确认的参与者别名表。

Qwen 结构抽取需要设置 `DASHSCOPE_API_KEY` 环境变量。Qwen 失败时仍会生成观察层画像。

---

## 致谢

Scriptorium 的文档系统（`scriptorium/documents/`）移植自 [MISAKA-Agent](https://github.com/Luciole-Studio/Misaka-Agent)（Copyright 2026 Luciole Studio, [Apache License 2.0](LICENSE-MISAKA)），包括内容寻址存储、层级大纲检测、引文归一化验证和多格式文本提取器。对抗性多视角辩证分析的架构设计亦受 MISAKA 多智能体编排的启发。详见 [NOTICE](NOTICE)。

---

MIT License
