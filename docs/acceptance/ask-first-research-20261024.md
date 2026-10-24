# 提问即研究（ask.v1）实施与验收记录

记录日期：2026-10-24  
范围：统一工作台对话框的“直接提问即可研究”能力  
状态：**已实现并通过自动化与浏览器验证；真实模型未调用，学术质量未评议。**

## 1. 交互

对话框默认方式是“提问”，不再要求先勾材料或选方法。输入问题后：

1. 服务检索本项目材料（Elasticsearch CJK 分析器）；检索不可用或没有命中时退回已就绪材料的顺序扫描；
2. 锁定阅读窗口（默认最多 8 段、24,000 字符），超出的窗口记为 `unread`，不静默截断；
3. 只依据这些材料回答，每条事实判断附逐字引文；引文按 code point 半开区间精确对齐，重复引文用 prefix/suffix 消歧，唯一性不成立就报错；
4. 生成 `research_answer` 记录，并在对话里给出回答与“原文 N”按钮；
5. 回答卡片上的“深入完整研究”把同一冻结范围交给完整方法流水线（构境／内在批判／视差／审查）。

选中材料或选区会收窄范围（`plan.retrieval=explicit`）；未选择时范围由检索决定（`search` 或 `material_scan`）。回答记录保留 `scope`、`plan`、`coverage`、`open_questions`、`followups` 与调用用量，便于复核与追加研究。

## 2. 实现位置

| 层 | 文件 | 内容 |
|---|---|---|
| 编排 | `scriptorium/research/ask.py` | 检索、窗口冻结、阅读与覆盖、引文对齐、记录与消息 |
| 接入 | `scriptorium/research/workspace.py` | `tool=ask` 路由；空范围允许自动检索 |
| 契约 | `scriptorium/research/unified_api.py`、`api.py` | `tool` 增加 `ask` 并设为默认；记录类型增加 `research_answer` |
| 前端 | `web/src/features/workspace/components/ResearchComposer.tsx` | “提问”置顶为默认，占位与范围提示说明自动检索 |
| 前端 | `web/src/features/workspace/UnifiedWorkspace.tsx` | 默认工具、回答卡片的“检索与覆盖”、一键“深入完整研究” |
| 契约 | `web/src/features/workspace/api/client.ts`、`generated.ts` | 回答记录字段；`SendIn.tool` 重新生成 |

错误码：`NO_MATERIALS_FOR_QUESTION`、`ANSWER_REQUIRES_CITATION`、`ANSWER_CLAIM_REQUIRES_CITATION`、`CITATION_AMBIGUOUS`、`CITATION_EXACT_QUOTE_NOT_FOUND`、`SEARCH_UNAVAILABLE`、`MODEL_NOT_CONFIGURED`。

## 3. 已验证证据

自动化（`tests/test_research_ask.py`，5 项）：

| 用例 | 断言 |
|---|---|
| 未选择材料时自动研究 | 自选范围、`plan.retrieval ∈ {search, material_scan}`、覆盖状态逐项记录、演示标记、会话内出现回答与产物 |
| 选择材料时只读所选 | `plan.retrieval=explicit`，范围仅含所选材料 |
| 空项目 | 任务失败并报 `NO_MATERIALS_FOR_QUESTION`，不生成记录 |
| 真实模式缺密钥 | 任务失败并报 `MODEL_NOT_CONFIGURED`，不退回演示 |
| 引文与深化 | 引文全部成为可定位锚点、调用写入 `r_model_calls`、`scope` 传给完整研究后运行范围一致 |

浏览器（`scripts/browser_acceptance.py`，20 项全部通过）：

- `ASK-01` 直接提问返回带检索说明的回答；
- `ASK-02` 回答记录含“检索与覆盖”；
- `ASK-03` 一键在同一范围展开完整研究。

截图：`output/acceptance-browser/05-demo-reply.png`、`05b-ask-answer.png`；结果：`output/acceptance-browser/browser-acceptance.json`。

工程：全量 `pytest` **359 passed, 2 skipped**（跳过为未配置的 S3 端到端；单独配置后 `test_research_s3_live.py` 4 项通过）；Ruff、前端构建与检查通过。验收库已升级到 `research_0004`（v4 事件与会话快照表）。

## 4. 边界（不得据此推断为通过）

- **真实模型未调用**：引文对齐与记录链路用受控替身验证；真实模型的回答质量、拒答与“材料不足”判断未验收。
- **检索质量**：结果取决于 ES 索引与查询措辞；未命中时退化为顺序扫描，可能挑到与问题弱相关的段落。回答记录会写明检索方式，但“挑得准不准”需要人工评议。
- **阅读上限**：默认 8 段／24,000 字符，属快速回答而不是穷尽研究；未覆盖窗口会列出。
- **无流式输出**：回答一次性写入，进度通过任务卡片显示；未做 token 级流式。
- **范围仅限当前项目**：不跨项目检索，避免绕过项目隔离与授权。
- 参考 [Misaka-Agent](https://github.com/Luciole-Studio/Misaka-Agent) 的“问题 → 来源与未决问题”交互组织，没有复制其代码、提示词或品牌资产；许可证记录见 [参考来源](agent-experience-references.md)。
