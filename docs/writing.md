# 用 Scriptorium 写论文

插件提供实际文稿存储与引用工具，正文由当前宿主模型撰写。下列调用顺序适用于 MCP；ACP 上下文模式不能独立调用宿主模型写论文。

## 1. 选择材料和问题

使用者自行导入。首次启动没有样本论文、书目或预加载题目。

`source_import` 接受主动提供的 `text`，或研究目录中的 UTF-8 TXT/Markdown `path`，两者择一。可设置 `title`、`citation` 和 `source_uri`。`source_kind` 分为 `text`、`excerpt`、`bibliography`。

书目元数据不能代替已阅读正文。URI 只记录来源，不自动下载；提取 PDF 和联网发现交给宿主工具。页码必须来自实际材料，不能从字符偏移推断。

以 `source_search` 找到相关段落，再通过 `source_read` 扩大上下文。`research_prepare(question, source_ids, methods, writing_genre="research_article")` 返回写作契约、方法字段和覆盖记录。阅读不足时继续调用窗口，不把有限检索结果写成全书结论。

## 2. 从提纲进入正文

调用 `manuscript_create(title, question)`，取得 `manuscript_id` 与 `revision`。同一工作区、相同标题与问题重复创建返回已有文稿，不清空内容。`research_status` 可以找回本工作区文稿 ID。

宿主按论文需要撰写摘要、引言、研究脉络、分节论证、反方意见、结论；并非所有文种都必须套同一模板。每段核心论证交代主张、证据、推论桥梁和适用限制，区分作者立场与研究者解释。

保存正文的调用形状：

```json
{
  "manuscript_id": "上一步返回的 ID",
  "section_id": "argument-1",
  "title": "第一节标题",
  "content": "这里是完整论证正文。[[cite:1]]",
  "expected_revision": 1,
  "position": 2,
  "citations": [{"source_id": "已导入原文的 ID", "quote": "实际原文摘录", "start": 0}]
}
```

这是参数说明，不是随包导入的示例文献。`start` 为 Unicode code point 偏移，可省略；摘录出现多次时必须提供准确位置。`[[cite:n]]` 与 `citations` 一一对应，序号从 1 开始。引述和转述都可以链接到作为依据的精确摘录；精确匹配不判断转述是否忠实。

写入时原子核验所有引用。不存在、重复未消歧或只有书目元数据的引用会阻断保存；不会静默删掉引用来制造成功。无引用章节允许保存，但导出会标明 `NO_LINKED_EVIDENCE`。文本中的普通引用格式不被自动识别为已核验引用。

每次保存返回新的整篇 `revision`，下一次保存必须使用它。单节最多 50,000 code points，整篇最多 200,000，最多 100 节、每节 50 条引用；超限需拆分研究文稿。

## 3. 修订和恢复

- `manuscript_read(manuscript_id)`：目录、顺序、当前修订。
- `manuscript_read(manuscript_id, section_id)`：章节正文、引用、历史修订号。
- 增删正文或调整章节 `position`：用当前修订再次 `manuscript_write_section`。
- `REVISION_CONFLICT`：先读取当前正文，再比较和合并；禁止盲目重试覆盖。
- `manuscript_read(..., revision)`：读取该章节某次历史快照。
- `manuscript_restore_section(..., revision, expected_revision)`：恢复为新的修订，不删除历史。

研究者决定哪些修改可接受。插件不把模型建议自动视为作者接受。关闭并重新启动宿主后，文稿与修订保留在同一工作区。

## 4. 导出可编辑论文

先完成所有保存，再调用 `manuscript_export(manuscript_id, expected_revision)`。

返回固定修订的 `markdown`、脚注和独立 `evidence_trace`；宿主使用自己的文件工具把文本保存到用户选定位置。导出事务期间的新修改不会改变本次快照。导出重新检查来源状态与散列；已撤回或损坏的引用不能继续导出。

Markdown 不依赖专有编辑器。DOCX、PDF 或期刊排版可由宿主已有转换工具完成，当前插件不内置 Pandoc、citeproc 或投稿系统。导出不会自动标为定稿或“通过学术审核”。

研究者仍需核查观点归属、论证支持、书目格式和未覆盖材料。没有用户真实经历时，不得把假设写成第一人称事实。不存在的文献、页码、访谈与实验结果不能补写为事实。
