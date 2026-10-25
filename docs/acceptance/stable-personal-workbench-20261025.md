# Scriptorium 3.3.0 个人研究工作台修缮验收记录

日期：2026-10-25。范围：用户批准的“从功能齐备转向稳定、顺手的个人研究产品”计划。服务器部署搁置；未调用付费模型，未组织学术评分，未正式迁移数据，最初按不提交／推送执行；用户随后明确授权提交并推送 GitHub，提交记录据此更新，未发布 Release。既有 README、tools、历史报告、旧库保留。

## 交付与版本依据

应用、Python 包、服务健康信息、Web、Tauri、Cargo 和启动画面统一为 3.3.0。Git 基线 `179c9e9158cdbf1ab68b194557c5df9f776ffa1e`，实际交付包括未提交改动，不能只用 HEAD 代表候选。

代码冻结摘要：`e895a19ed50db6a4bfd811319531d32aabf8db7f58e8d4c50939c6ccfcb2db8c`。计算规则与明细见 [源代码摘要](evidence-20261025-stability/stability-source-digest.json)，不含文档、临时数据、日志及构建产物。候选安装包和后端的独立散列见 [候选产物记录](evidence-20261025-stability/stability-candidate-hashes.json)。

冻结前复查补齐了手动切换章节的过期草稿恢复；第一次后端收集已中止，修复及浏览器复核后重新生成最终候选。未安装中途产物。随后标准输出路径被已有桌面服务占用，覆盖返回 WinError 5；没有停止该服务，改用独立 staging 输出，并只更新安装用的目标架构 sidecar。失败日志保留于 `output/stability-sidecar-build.log`，最终构建以 `output/stability-sidecar-stage-build.log` 为准。

提交前只规范化了一个 TypeScript 接口文件的末尾空行，重新构建并逐文件校验 Web 静态产物散列全部一致，无需重复打包。

本轮没有表结构变更：工作区、文稿、任务采用现有表的 JSON 扩展及读取接口。历史 Alembic 修订未改写，不需要新增空迁移。

## 实际改动

| 操作链 | 改动及代码位置 |
|---|---|
| 会话切换 | `UnifiedWorkspace.tsx` 统一暂态清理、请求取消与迟到结果检查；选区、方法、模式、流式草稿、文档历史属于会话；按用户、项目、会话恢复工作区 |
| 保存与冲突 | `save-queue.ts`、`ArtifactWorkspace.tsx` 共用保存队列，排空请求期间的新编辑；章节切换、建议接受和导出等待保存；冲突可比较、采用远端或另存本机副本 |
| 导出 | `manuscripts.py`、`exporting.py` 提交时冻结主稿、章节修订及引用书目；相同幂等请求返回同一任务；后续编辑不改变已提交导出；撤权仍阻断下载 |
| 写作 | 章节目录、排序、字数、章节级建议、修改增删显示、版本恢复；引用显示书名、作者和页码；笔记／报告可插入当前主稿或章节 |
| 材料及整理 | `ProjectSidebar.tsx`、`ImportQueue.tsx` 提供搜索、用途／状态筛选、批量顺序登记及 SHA-256 重复提示；撤回材料不进入正常列表；笔记与报告按类型筛选、固定、归档并关联研究问题 |
| 书目 | `BibliographyForm.tsx`、`bibliography.ts` 支持本地专著、译著、期刊字段与 CSL JSON 导入；缺失字段提示；多条 CSL 可选择条目后保存 |
| 结构化结果 | `ResearchFields.tsx` 分别编辑论点／构境配置、证据及未决问题；与报告正文编辑分开，以修订检查保存 |
| 服务端数据 | `useProjectResources.ts` 由 TanStack Query 实际拥有项目资源缓存；记录、任务和调用账本读取摘要；事件按资源刷新，断线才启用整项目轮询降级 |
| 持久任务 | `useArtifactTasks.ts` 替换组件固定九十秒等待；任务在离开页面后仍可找回，支持失败重试、停止及重新下载；非当前会话的活跃任务允许低频补查 |
| 阅读分页 | `reading.py` 只返回当前版本的阅读窗口；通常每页不超过 6000 code points 或 40 段，引用跨界时扩大窗口以完整显示引用；保持原片段偏移 |
| 客户端与服务 | `contracts.py` 补齐会话、决定、章节、阅读、引用标签等响应；`api/artifacts.ts`、`api/reading.ts` 使用生成类型；章节保存、接受建议、导出复用 `manuscripts.py` |
| 个人模式 | 项目设置优先呈现材料／导出／备份；治理设置与旧专业工具保留在展开入口；不删除旧业务数据 |

首次提问仅在会话仍为默认名称时，根据问题截取短标题，不另发模型调用；用户已有名称保留。

## 必要检查与证据

| 检查 | 结果 |
|---|---|
| PostgreSQL 针对性集成 | **14 passed**，31.18s；`test_stable_writing.py` 5 项与 `test_integrated_workbench.py` 9 项；见 [日志](evidence-20261025-stability/stability-final-backend-tests.log) |
| 前端逻辑 | **8 passed**：保存请求共享与失败、请求期间新编辑、Unicode 差异、CSL、阅读窗口与标签恢复；见 [日志](evidence-20261025-stability/stability-frontend-tests.log) |
| 类型与生产构建 | `npm --prefix web run build:tauri` 通过，含 TypeScript；见 [日志](evidence-20261025-stability/stability-build.log) |
| 代码检查 | OXLint 与 Ruff 通过；见 [前端](evidence-20261025-stability/stability-frontend-lint.log)、[Python](evidence-20261025-stability/stability-python-lint.log) |
| 生成接口 | `generate-api-types.py --check` 通过；历史 v1 重复 Operation ID 警告保留，没有作为新错误处理；见 [日志](evidence-20261025-stability/stability-contract-check.log) |
| 浏览器桌面 | 编辑后立即换章节再返回内容完整；导出任务完成并显示修订／格式／时间；制造远端冲突后比较并另存本机草稿成功 |
| 会话隔离 | 引文回跳产生选区；切至独立会话后无选区及旧文档，返回原会话恢复自身选区与文档；刷新恢复文稿和工作区 |
| 480px 窄屏 | 单文档视图完成原文笔记保存、引用与笔记插入当前文稿；临时视口已恢复 |
| 浏览器日志 | 最后一次刷新后的工作台未发现 console error／warn |
| 固定导出快照 | 集成测试在提交后修改主稿与章节，再执行真实 Pandoc HTML 导出；文件含提交时正文，不含后续修改 |
| 权限与恢复关联 | 受影响集成文件包含只读／评议者边界、私有工作区、章节历史、过期建议、备份恢复及中断调用记账；不等同于重新验证全部旧能力 |
| 二进制冒烟 | **通过**：staging 后端在独立库启动 API／Worker，导入材料、分页读取、创建章节、固定版本 DOCX 导出（10632 bytes）、静态入口 JS 及零付费调用；见 [记录](evidence-20261025-stability/stability-packaged-smoke.json) |
| Windows 候选 | **构建通过**，3.3.0 NSIS（124.19 MiB）；未安装到用户正式目录。安装 sidecar 与实际冒烟后端散列一致；见 [构建日志](evidence-20261025-stability/stability-desktop-build.log) |

早期新增测试曾因夹具错误假设材料导入后的修订为 1 而失败，已改为读取实际修订；随后定向复测通过，最终以上 14 项合并运行全部通过。保留旧失败日志，不以增加累计次数掩盖失败。

测试使用 PostgreSQL `127.0.0.1:55432` 的独立测试 schema；浏览器使用独立库 `scriptorium_stability_preview_20261025`、API 8034 及合成材料。运行配置限制调用预算，未产生付费请求。未写入当前用户正式研究库。

### 界面证据

- [工作台与刷新恢复](evidence-20261025-stability/workbench.png)
- [远端冲突与本机草稿比较](evidence-20261025-stability/conflict.png)
- [原文版本定位与范围](evidence-20261025-stability/reading.png)
- [手动切换章节时恢复过期草稿](evidence-20261025-stability/chapter-draft-recovery.png)
- [480px 写作与来源插入](evidence-20261025-stability/narrow-writing.png)

## 本轮边界与仍待细化

- 完成的是稳定性主链及增量架构收敛，并未把所有旧调用一次改写为生成 SDK，也未彻底拆空 `UnifiedWorkspace`。新阅读／文稿接口采用生成类型，其余仍有兼容包装。
- 服务端阅读窗口避免整篇正文传输，但仍读取该版本全部片段 ID 与长度以计算分页；尚未实现超大材料的持久分页目录。显式“版本比较”的兼容接口仍可能读取全文。
- 增删比较按共同前后缀划定变动区，不是精细逐词修订或协同编辑算法。
- 任务列表保留最多 250 条且优先活跃任务，单文稿界面显示最近 20 条；本轮没有实现无限历史分页。
- 旧的已排队导出若没有 snapshot 字段仍按兼容流程处理；本轮新提交导出固定修订。
- 本地重复文件是提示与显式选择，不跨项目合并材料身份；CSL 本地导入不包含联网元数据补全。
- 本轮不重新验证所有专业旧业务、中文输入法候选窗口、全部键盘路径、安静模式及所有断线／崩溃排列；既有能力保留，未执行不记通过。
- 不进行正式数据切换、不删除旧库、不在用户当前安装上执行升级；候选包的完整干净用户安装、升级与卸载矩阵未验证。
- 服务器部署、付费模型重跑、学术质量评价、大规模压测、长期稳定性及正式安全认证按用户范围跳过。

安装包文件：`Scriptorium Agent_3.3.0_x64-setup.exe`，130226807 bytes。SHA-256：`e5aa6b1cd4922f2038f400f278bcb51d1f33228107868723b1c98a08fe0798c0`。大型安装包仅本地保留。

## GitHub 提交范围

仅提交代码、测试、说明与必要证据。排除密钥、研究库、对象原件、临时预览数据、构建缓存及大型安装包。候选包本地保存，散列随验收记录提交；不创建 Release 或自动安装。

## 交付使用

个人版以新的 3.3.0 NSIS 候选为准。现有 3.2.0 安装包不含本轮修改。建议先在保留备份的个人测试项目检查真实材料操作，再自行决定安装及正式数据使用。操作说明见 [个人研究工作台说明](../personal-workbench-runbook.md)。
