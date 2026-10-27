# Scriptorium 3.6.0 插件交付检查

日期：2026-10-27。产品由独立工作台转为 ACP/MCP 研究与论文写作插件。

## 交付范围

- 12 个 MCP 工具与 ACP v1 上下文子集，共用工作区材料内核。
- 新增专用 SQLite；创建文稿、章节正文保存、精确引用、修订冲突、历史恢复、固定版本 Markdown 导出。
- 旧前后端、常驻服务、数据库迁移、安装器和旧工具入口从当前 Git 树移除。旧恢复点 `62336a8e83cdf90a138829e939284cfe7fda18dd`。
- 保留实际用户数据与备份。按用户最新确认，仅推送代码、文档与配置模板；用户题目、推荐材料、聊天、模型草稿、SQLite 和密钥不上传。
- README 与原创 SVG 横幅、宿主接入和写作指南；依赖 Pydantic/MCP，模型和网络工具由宿主提供。

## 本轮检查

| 检查 | 结果 |
|---|---|
| Ruff 检查 | 通过 |
| 插件定向测试 | 17 passed；包含工作区隔离、Unicode、重复引用、撤回/散列、文稿冲突、历史、重启、ACP 取消及 stdio |
| doctor | 3.6.0，MCP 可用，无桌面/PostgreSQL要求 |
| 实际 MCP SDK | stdio 初始化、列工具、导入、检索、引用、上下文、章节保存和导出通过 |
| 独立安装 | 新建无 system-site-packages 的 Python 3.12 虚拟环境安装最终 wheel；在源码目录外重复实际 MCP 调用通过 |
| wheel 内容 | 仅插件包、元数据和许可证；没有 GUI、旧服务、用户数据库或材料 |
| 用户数据 | 本轮仅检查/隔离测试输出；未切换或删除旧数据 |

插件写作工具验证采用合成正文，验证持久化与引用链，不冒充已完成论文质量评审。此前单次 Qwen 连接耗用 2,708 token 为历史记录；本轮没有追加付费调用，也不分发其材料和草稿。

## 包与来源绑定

下列候选位于本机 `output/scriptorium-3.6.0/`，不自动创建 GitHub Release。ZIP 含 wheel、安装说明、配置模板和指南；pip 安装仍需下载依赖，不是离线运行包。

- `scriptorium-3.6.0-py3-none-any.whl`：32619 bytes，SHA-256 `c29bcec75d64b2429fc82888bcee2e80421dd8c6d3267ed58b6c8f634254addc`。
- `scriptorium-3.6.0-plugin.zip`：52377 bytes，SHA-256 `f478ac961be93878daecfeff7982739d4012afa83cc443ce625190367d6f83fd`。

包输入散列：`25ed4c1b549bb88274f50ddc68f699b27748b9b5e8834087cf2e827bd8c91f5a`。完整文件散列在同目录 `manifest.json`，绑定 Python 实现、pyproject、README 与许可文件。

## 未验证与保留边界

- 原生 Codex 工具需会话重载；本次 SDK 验证不等同于原生宿主验收。测试连接已改为空工作区，不加载用户题目。
- DSH、Qoder、Zed、Cursor、Claude Code 和 VS Code 的原生安装未实测；只提供对应配置并记录协议测试。
- ACP 是上下文 Agent，尚不能独立调用模型生成整篇论文。MCP 由宿主模型实际写作，插件负责保存、引用和版本。
- 未进行学术质量评分、投稿认证、PDF/OCR、DOCX 排版、服务器部署、GUI/桌面打包或全平台安装矩阵。
- 构建首次在缺少 Hatchling 的全局 Python 下失败；随后使用含构建依赖的独立构建环境成功。独立运行环境只安装发布 wheel 与运行依赖。
