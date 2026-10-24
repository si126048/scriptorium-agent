# 统一工作台设计规范与组件样例

更新：2026-10-24。实际样式以 `web/src/features/workspace/experience.css` 为准，基础布局沿用 `workspace.css`。

## 视觉与布局

暖白阅读纸面、浅暖灰背景、深绿灰正文；橙色只用于关键操作、引用和当前状态。正文 16px，原文 18px、行距 1.95，编号及技术标签使用等宽字体。保留原品牌与图标。

项目和会话位于左侧，对话居中，原文、报告和文稿共用右侧文档区。850px 以下打开文档会切换到阅读视图，侧栏作为抽屉；关闭或返回文档可继续原会话。文档宽度支持拖动及方向键。每个项目的会话、草稿、文本版本、阅读位置独立保存。

## 动效与无障碍

按钮约 120ms，菜单约 180ms，文档面板约 240ms。引用高亮只执行一次。MotionConfig 接受系统减少动态效果设置；安静模式禁用转场，CSS 同步关闭动画和滚动过渡。启动默认 1.8 秒、每会话一次，保留跳过及明确选择的交互播放。模型无真实总量时不生成百分比。

Radix Dialog 管理对话框焦点；研究工具使用 DropdownMenu，配置使用 Collapsible。中文输入法组合输入期间不发送 Ctrl+Enter。引文节点可通过键盘打开。窄屏浏览器验证图片见 `output/browser-upgrade/`。

## 实际组件与示例

| 组件 | 职责 | 状态样例 |
|---|---|---|
| `ResearchComposer` | 输入、附件、研究工具、范围、选项 | 无材料普通对话、精确选区、真实/演示、访谈回答 |
| `DocumentPane` | 文档面板、键盘与指针宽度调整 | 报告、阅读、稿件；窄屏单区 |
| `ResearchProgress` | 阶段、任务、用量和取消 | 排队、执行中、未知消耗保留；不制造百分比 |
| `CitationReview` | 多处引文逐项重绑与不采用 | 位置不唯一、摘录不存在、部分解决 |
| `ManuscriptEditor` | Tiptap 可视化稿件 | 标题、列表、编号、引述、脚注、引用、撤销、自动保存 |
| `ReportGraph` | 研究图与概念图独立呈现 | 按需加载、打开对应来源 |
| `DialogProvider` | 应用内输入与确认 | 新建项目、重命名、脚注 |

```tsx
<ResearchProgress jobs={[]} usage={{used_tokens: 4200, unknown_calls: 1}} onCancel={cancel} />
<DocumentPane width={560} onResize={setWidth}>{document}</DocumentPane>
<ManuscriptEditor recordId={record.id} value={record.payload.editor_json}
  source={record.payload.text || ''} evidenceIds={record.payload.evidence_ids || []}
  onChange={saveDraft} onLocate={openSource} />
```

编辑器 JSON 是写作源，Markdown 由服务端重建；旧 Markdown 无法安全转换的块作为原文块保留。引用节点只保存锚点身份，服务端递归验证项目、材料状态和摘录一致性。章节有独立修订检查和导出，旧版本保存在修订记录。学术结论仍为待评议候选。

## 已知后续项

工作台已抽出输入、文档、进度、编辑、引用核验和图组件，项目导航和旧业务设置仍可继续拆小。当前主工作台 JS chunk 仍超过 500KB（编辑器和图已延迟加载）；应继续拆分公式渲染及业务设置。未把构建通过当作完整键盘、屏幕阅读器及系统 IME 验收。
