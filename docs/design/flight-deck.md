# FLIGHT DECK 设计系统（3.5 落地记录）

中性 NASA-punk 方向：哑光米灰面板、石墨字、安全橙信号、缝线、仪表、检查单。
本文件记录已落地的 token、组件与边界；静态样张见 [flight-deck/](flight-deck/README.md)。

## Token

唯一来源：`web/src/features/workspace/design-tokens.css`。

| 类别 | 变量 | 白班 | 夜班 |
|---|---|---|---|
| 纸面 | `--fd-paper` | `#F5F3EC` | `#1B1C1E` |
| 面板 | `--fd-panel` | `#ECE9E1` | `#232528` |
| 底板 | `--fd-hull` | `#DCD8CE` | `#17181A` |
| 正文 | `--fd-ink` | `#1B1C1A` | `#E9E6DC` |
| 次级 | `--fd-ink-2` | `#4A4B46` | `#B9B6AC` |
| 缝线 | `--fd-seam` | `#C7C2B5` | `#35332E` |
| 当前/主行动 | `--fd-orange` | `#C25A22` | `#E07A3F` |
| 证据/引文 | `--fd-amber` | `#8F651C` | `#D6A44E` |
| 理论/象征 | `--fd-teal` | `#3F5F63` | `#7FA3A6` |
| 成功 | `--fd-green` | `#45664A` | `#8FB08F` |
| 失败 | `--fd-red` | `#A33A2C` | `#E07A6A` |

字体：`--fd-ui` = Bahnschrift / 微软雅黑 / Segoe UI；`--fd-mono` = Cascadia Mono / Consolas。
动效：`--m-fast 120ms`、`--m-base 180ms`、`--m-panel 240ms`、`--m-gauge 400ms`。
圆角 2px，无阴影（浮层除外），1px 缝线。

## 已落地

- **任务条**（`MissionBar`）：本地连接灯、项目/会话、`RUN xxxx`、token 圆环、来源/任务计数、HALO 与 DAY/NIGHT 拨杆、搜索与菜单。
- **导航轨**：字标、项目选择器、新建研究、搜索、模块计数；选中项 2px 橙左线。
- **任务台扉页**：`RESEARCH INSTRUMENT · STANDBY`、目录式起始项 `01/02/03`、导入材料 / 开始访谈。
- **飞行日志**：3.5 `rt-*` 时间线的编号计数器、缝线、状态章 `DONE/RUNNING/STREAM/HOLD/FAILED/PARTIAL/QUEUED`；AUTO 记录用青色章。
- **视场**：文档区舷窗角标、通道标签、文稿工具栏、来源清单化、浮动选区、失败 caution 面板。
- **HALOFLUX 环境光**（可选，默认关）：任务条 HALO 拨杆；同源 iframe、低透明度、暗角；打开自动切夜班。授权为非商业组件，见 [README 第三方视觉组件](../../README.md#第三方视觉组件)。

## 未完成

- `workbench.css` 仍有约 190 处硬编码颜色；夜班下少数遗留面板仍偏亮，需逐条迁移到 token。
- 动效只落地了拨杆、状态章与基础过渡；仪表摆针、阶段打勾、引文连线尚未实现。
- 浏览器验收脚本仍在跟 3.5 结构对齐；`scripts/verify_flightdeck.py` 覆盖任务条/项目/时间线/选区/主题/480，但等待时序尚未稳定。
- 未做完整的对比度自动化与 480px 全流程截图。

## 验收边界

静态样张用于方向确认；真实运行截图在 `output/design-samples/`（不随仓库分发）。任何“视觉验收通过”的说法都必须附当轮截图与 CI 结果。
