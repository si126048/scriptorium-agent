# Scriptorium 3.6 插件转向与宿主兼容

核查日期：2026-10-27。默认产品由独立研究工作台改为宿主 Agent 的研究工具包。

## 一个内核、两个接口

MCP 是主要执行入口：材料导入、检索、原文窗口、精确引文核验、方法与覆盖上下文均返回结构化对象。模型使用宿主原有配置；插件没有调用宿主模型的神奇通道，也不自动取得宿主密钥。

ACP v1 是上下文 Agent 入口，支持 initialize、session/new、session/prompt、session/cancel、session/close。文本和嵌入文本进入同一材料内核。返回值明确是研究交接包，不伪装成模型已经完成的解释。当前不支持 session/load、图像/音频、外部 MCP 附加、客户端文件/终端调用、独立模型推理；不宣称覆盖 ACP 的所有能力。

stdout 仅输出协议，进度来自实际本地操作，不把完整回答分段伪装成模型流式输出。取消是协作式，本地步骤结束检查取消；没有无法计费审计的后台模型任务。

## 宿主兼容范围

| 宿主 | 入口 | 本轮状态 |
|---|---|---|
| Codex | MCP stdio；生成 config.toml 片段 | 实际 MCP SDK 调用通过；原生工具加载状态另行记录 |
| Cursor / Claude Code / Qoder | MCP stdio 的 mcpServers 片段 | 配置已生成；未执行这些产品的原生安装验收 |
| VS Code | MCP servers 片段 | 配置已生成；宿主未实测 |
| Zed / 其他 ACP 客户端 | 自定义 Agent / stdio | ACP 子进程协议测试通过；Zed 未安装实测 |
| DeepSeek Harness | `@deepseek-ai/dsh-mcp-client` stdio 插件条目 | 官方配置形状已核查；本机未发现 dsh，未宣称宿主实测 |

示例在 `integrations/`。其中 `/ABSOLUTE/PATH/TO/WORKSPACE` 必须替换。优先运行 `scriptorium config --host ... --workspace ...` 生成当前机器的绝对路径；虚拟环境用 `--python` 指定 Python。片段需要合并，不能覆盖已有宿主配置。

DSH 的 `integrations/dsh.json` 是 JSON 形式的 YAML 兼容条目数组，供合并到对应 Cordis scope；它不是 npm 插件安装清单。配置使用 `serverName: scriptorium`，工具命名由 DSH 桥生成。当前 MCP SDK 测得协商版本 2025-11-25；DSH 官方文档说明可回退受支持的旧协议，未因此宣称其最新协议专属功能已通过。

## 研究材料边界

- 只导入主动提交的文本或指定的工作区内 TXT/Markdown 文件；不扫描仓库，不读取隐藏路径，不跟随符号链接越出工作区，不自动读取旧数据库。
- 默认库 `.scriptorium/research.sqlite3` 已加入 Git 忽略；普通材料不创建虚构参与者。
- `text`、`excerpt` 和 `bibliography` 分开记录。同内容、同类型去重；正文修订产生新 ID。书目中的匹配返回 `quote_scope=bibliographic_metadata`，不能作为正文原话。
- 精确摘录固定到内容散列和 Unicode code point 范围；重复摘录必须消歧。引用可定位不等于支持结论。
- `research_prepare` 的输出状态为 `awaiting_host_inference`。它提供构境、内在批判、视差的操作约束，不执行或冒充这些分析；明确列出覆盖与未覆盖文本。
- 网络发现、正文获取、模型推理、文件输出交给宿主的已授权工具，避免再维护一套 GUI、供应商调度和来源下载器。当前插件不自动调用旧服务；旧服务已从当前代码删除；需查阅旧业务时使用独立历史检出。

## 学术写作约束

`research_prepare.writing_genre` 支持 `research_note`、`argumentative_essay`、`research_article`、`literature_review`。输出写作契约和所选方法的字段要求。每个论证单元区分主张、主张类型、来源、推论桥梁、反方意见与限制；不会把引用匹配率当作学术质量评分。

构境需交代问题关系、概念配置和阅读者位置；内在批判先明确自身尺度；视差比较先排除可消解的差异。材料不足可以停止或保留空缺，不通过堆砌理论术语生成貌似深刻的结论。

书目仅支持元数据陈述；作者立场、原文引语和文献综述须以实际阅读为基础。个人反思必须基于用户明确提供的事实；没有经历时留待填写，或把整段标为假设。日常论说题也应清楚论证，但不能强行套期刊研究方法与综述形式。

这些是供宿主模型遵循、供用户检查的结构化约束。当前没有自动学术认证；Qwen 的第一次草稿未因生成成功而通过。新写作契约加入后没有追加付费模型调用。

## 论文工具

MCP 提供 12 个工具，其中 5 个用于真实文稿的创建、章节保存、读取、恢复和导出。完整参数见 [论文工作流](writing.md)。章节正文、引用与历史存入本地库，保存核验修订号，导出绑定固定版本；它们不依赖旧 Web 或 PostgreSQL。

宿主负责生成全文并调用工具，不能将 `research_prepare` 的上下文包当作完成的论文。当前 ACP 是上下文适配，不能宣称自行调用宿主模型写作；需要论文工作流时优先通过 MCP。

## 清理与保留

当前仅保留 Python 插件、协议测试、配置片段、构建与文档。直接依赖为 Pydantic 与 MCP 两项。旧前后端、安装器、常驻服务、迁移和旧业务模块从 Git 树移除；不存在兼容启动入口。迁移和历史恢复点见 [迁移说明](migration.md)。

已有用户数据、输出、源库、桌面目录和备份不删除。首次资料库为空，使用者选择导入；分发包不含测试用户的题目、书目、模型草稿或密钥。常规验证使用临时合成材料，Qwen 可选测试必须显式开启，密钥从环境变量读取。

## 依据

- [ACP v1 初始化](https://agentclientprotocol.com/protocol/v1/initialization)、[会话](https://agentclientprotocol.com/protocol/v1/session-setup)、[内容块](https://agentclientprotocol.com/protocol/v1/content)。本轮使用 v1 子集。
- [Codex MCP 官方说明](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)：配置与当前会话工具可见性须区分。
- [DeepSeek Harness 官方 MCP 桥](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)。
- [Qoder ACP 官方说明](https://docs.qoder.com/cli/acp)：Qoder 的 ACP 入口是其 Agent 服务端，因此本轮为加载外部工具提供 MCP 配置。
