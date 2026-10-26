# FLIGHT DECK 静态样张（3.5 方向评审）

中性 NASA-punk 方向的三张静态样张，用于在改动应用代码前确认视觉语言。样张是独立 HTML/CSS，不引入依赖，不参与构建。

- `console.html` — 任务台：导航轨、任务条、飞行日志、指令台、清单视场、证据 PLOT。
- `reading.html` — 阅读视场：17.5px/1.9 正文、琥珀引文角标、右侧 apparatus 边注。
- `boot.html` — 启动检查单：SYS/DB/MODEL/LINK 四步、进度、进入/日志/连接已有服务。

截图：`console.png`、`reading.png`、`boot.png`（1440×900）。

评审要点：

1. 米灰 + 石墨 + 安全橙的中性程度，是否够“航天任务台”而不土味。
2. 飞行日志的密度：编号、时间、状态章、AUTO/REVIEW 行是否清楚。
3. 阅读视场的字号、行宽与边注位置。
4. 启动检查单是否让人愿意等待首次安装。
5. 动效只写在规范里（拨杆、仪表、盖章、扫描），样张为静态。

正式实现时 token 落到 `web/src/features/workspace/design-tokens.css`，类名与 3.5 的 `rt-*`/`wb-*` 保持兼容。
