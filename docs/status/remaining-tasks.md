# Scriptorium 未完成任务统计

快照时间：2026-10-27（Asia/Shanghai）
仓库：`main` @ `8bbf5d7`
目标状态：**paused**（rounds 23/24，需用户在界面恢复后才能自动继续）
工作区：`docs/design/flight-deck.md` 有未提交改动（本轮验收记录）

## 状态快照

| 项 | 状态 |
|---|---|
| 前端构建 | 通过 |
| `oxlint` | 0 警告 |
| `ruff` | 通过 |
| 浏览器验收 | 12/12（独立 headless Edge） |
| 全量测试 | 427 passed / 2 skipped（2026-10-27） |
| CI | `8bbf5d7` 上次查询为 in_progress；更早提交 success |
| 未提交 | 1 个文档 |

## 已完成（摘要）

- FLIGHT DECK token/主题、任务条、导航轨、任务台扉页
- 飞行日志 `rt-*` 样式、状态章、AUTO 章
- 视场/来源清单/浮动选区/文稿工具栏
- HALOFLUX 环境光层（含非商业授权与归属）
- 机械动效基础（拨杆、勾号、章、仪表、发送键）
- 后端 AUTO 默认、引文清洗、writer 单次重试、预算上限放宽、预算到顶 `partial_completed`
- 验收脚本 12 项：任务条、项目、时间线快照、阅读器、选区、笔记、证据回跳、导出、白班/夜班对比度、主题、480

## 未完成任务

### P0 收尾（必须）

| ID | 事项 | 状态 | 下一步 |
|---|---|---|---|
| P0-1 | 提交 `docs/design/flight-deck.md` 验收记录与最终截图章节 | 未提交 | `git add docs/design/flight-deck.md && git commit && git push` |
| P0-2 | 收集本轮全量测试结果 | 已完成 | 427 passed / 2 skipped |
| P0-3 | 确认 `8bbf5d7` CI | 未确认 | GitHub Actions 查询；rate limit 时稍后重试 |

### P1 验收缺口

| ID | 事项 | 现状 | 影响 |
|---|---|---|---|
| P1-1 | 480 宽度完整流程 | 只验证不横向溢出 | 窄屏下发问、选区、导出未回归 |
| P1-2 | 全站对比度扫描 | 只查 5 个代表元素 | 局部小字可能低于 AA |
| P1-3 | 键盘焦点与焦点顺序 | 未测 | 可访问性未闭环 |
| P1-4 | 真实 AUTO 预算到顶截图 | 后端有单测，前端未出图 | AUTO 阶段成果的视觉未验收 |

### P2 视觉与脚本残余

| ID | 事项 | 现状 | 备注 |
|---|---|---|---|
| P2-1 | `workbench.css` 一次性 tint 色值 | 约 150 处 | 主要面板已 token 化，局部可继续 |
| P2-2 | 深色文稿标签条观感 | 计算样式均为深色（`rgb(27,28,30)`），截图有浅色合成层 | 需在真实非 headless 浏览器复核 |
| P2-3 | 动效细节 | 仪表摆针、引文连线未做 | 基础过渡已可用 |
| P2-4 | 旧 `browser_acceptance.py` | 3.5 半适配，后半段仍失败 | 由 `verify_flightdeck.py` 取代中 |
| P2-5 | 验收脚本未进 CI | 依赖本地 API/浏览器 | 可考虑 nightly 或本地 gate |

### P3 后端 AUTO 残余

| ID | 事项 | 现状 | 风险 |
|---|---|---|---|
| P3-1 | 预算到顶端到端测试 | 仅单测 `budget_partial` | 真实 worker/时间线未跑 |
| P3-2 | REVIEW 决策抽屉 UI | 未重构 | 人工复核流程仍是旧样式 |
| P3-3 | STEP 模式 UI 细化 | 已有「逐步确认」开关 | 决策到恢复的完整链路未验收 |

## 建议顺序

1. **P0-3**：确认测试与 CI（测试已完成）
2. **P0-1**：提交并推送文档
3. **P1-2 / P1-3**：对比度扫描 + 键盘焦点
4. **P1-1**：480 全流程
5. **P3-1**：AUTO 到顶端到端
6. P2 清理（不阻塞）

## 复现命令

```powershell
# 前端
npm --prefix web run build
npm --prefix web run lint

# 全量测试（PG/ES 已启动）
$env:SCRIPTORIUM_TEST_DATABASE_URL='postgresql+psycopg://research@127.0.0.1:55432/hermeneut_test'
$env:SCRIPTORIUM_TEST_ELASTICSEARCH_URL='http://127.0.0.1:59200'
python -m pytest -q --tb=short

# 浏览器验收（先独立启动 headless Edge）
python scripts/verify_flightdeck.py --no-launch --port 9576 --out output/acceptance-browser
```

## 阻塞与风险

- 目标处于 **paused**，模型无法自行恢复；需要用户在界面恢复后才会继续自动轮次。
- GitHub API 曾出现 rate limit，CI 查询可能暂时不可用；不代表构建失败。
- 浏览器验收依赖本地 API、worker、PG/ES；服务未启动时会直接失败。
- `verify_flightdeck.py` 不能在长期复用的 headless Edge 上跑，必须独立端口 + 独立 profile。

## 验收边界

静态样张用于方向确认；真实运行截图在 `output/design-samples/`（不随仓库分发）。任何“视觉验收通过”的说法都必须附当轮截图与 CI 结果。
