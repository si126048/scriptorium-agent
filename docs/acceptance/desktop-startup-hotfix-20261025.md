# Scriptorium 3.3.1 桌面启动修复

日期：2026-10-25。用户安装 3.3.0 后先出现 `LOCAL_DEPENDENCY_COMMAND_FAILED:psql.exe`，随后出现“服务已就绪 / research services not ready”。本记录独立于 3.3.0 验收，不能把之前未执行的首次冷启动视作通过。

## 根因与修复

1. PostgreSQL 开始监听 TCP 时仍可能恢复或初始化。原启动器直接运行 psql，收到 `the database system is starting up` 后错误地终止了整个服务。改用 `pg_isready` 等待数据库真正可接受连接，支持退出检查、取消及 120 秒上限。SQL 认证或实际命令失败仍立即返回，不以无限重试掩盖。
2. 桌面取得连接信息时启动完整 PyInstaller 后端，并设置 8 秒超时。解压或进程初始化超时后，轮询再次启动连接助手，旧助手未退出，造成进程积累。桌面现在直接读取安装清单及当前用户 Windows Credential Manager，不为读取连接启动子进程，也不把凭证写入文件。
3. PostgreSQL Windows 工具的本地编码被按 UTF-8 强制解码，导致中文错误乱码；现在优先 UTF-8，再尝试系统编码。保留更完整错误摘要，并展示数据库／检索等待阶段。全文检索首次启动允许最多 300 秒等待端口，健康检查仍另有上限。

代码：`scriptorium/research/local_runtime.py`、`src-tauri/src/native_connection.rs`、`src-tauri/src/commands.rs`、`web/src/features/desktop/DesktopGate.tsx`。应用相关版本统一为 3.3.1，未改动业务表结构或历史迁移。

## 当前验证

- Python 针对性测试：6 passed，覆盖暂时拒绝连接、无响应、正常就绪、进程退出、取消、超时、非法探测及中文解码。
- Rust 针对性测试：3 passed，包括读取本机真实已安装凭证，运行 0.01 秒；未打印密钥。验证只返回连接所需字段，并拒绝非法端口。
- Web 类型与生产构建、OXLint、修改范围 Ruff 通过。
- 用户本机后台已恢复 `running`；健康接口 200，search enabled，带认证项目接口 200。没有重建用户数据库、替换凭证或删除材料。
- 卡住的旧桌面启动窗口及该安装路径下超时遗留的只读连接助手已停止；恢复后的 Python 管理器、PostgreSQL、检索、API 和 Worker 保留。
- **打包后原生冷启动通过**：独立集群观察到 `postgres_wait → schema → api → done`，API 及 Worker 正常，材料导入 succeeded，调用账本为空。首次导入检查漏传幂等头而返回 422，修正测试脚本后复测通过，保留首次失败日志；生产接口保持原有约束。
- **NSIS 候选构建通过**：3.3.1，124.20 MiB；安装所用 sidecar 与冷启动验证的二进制 SHA-256 一致。
- 证据：[Python 测试](evidence-20261025-startup-hotfix/postgres-startup-hotfix-tests.log)、[原生凭证测试](evidence-20261025-startup-hotfix/postgres-hotfix-native-connection-tests.log)、[冷启动与导入](evidence-20261025-startup-hotfix/postgres-hotfix-native-check.json)、[安装包构建](evidence-20261025-startup-hotfix/postgres-hotfix-desktop-build.log)、[源代码及产物散列](evidence-20261025-startup-hotfix/candidate-hashes.json)。
- 按用户最终要求，没有再次打开界面；完整安装/升级 UI 与完整检索模式的候选冷启动未重跑，不记为通过。

## 数据与使用边界

排障期间曾通过修正后的源码管理器恢复本机后台，健康及授权接口均通过；临时排障进程后续已退出，原运行清单为 stopped。永久修复需使用 3.3.1 桌面候选；不要反复打开旧版启动页。候选不会自动正式迁移旧研究数据。现有研究目录、原件、凭证和旧安装包保留。

新增冷启动检查使用仓库 tmp 中独立集群，复用已验证组件，关闭测试检索与开机自启；不能因此宣称已重新验证所有组件的首次网络下载、不同 Windows 用户及升级卸载矩阵。

本轮未调用付费模型、未进行学术能力验证、未提交或推送本次修复，也未发布 Release。


## 候选使用

关闭旧窗口后运行 `src-tauri/target/release/bundle/nsis/Scriptorium Agent_3.3.1_x64-setup.exe`，选择原安装目录覆盖升级。安装沿用已有组件和研究目录，不需要删除研究数据。

安装包 SHA-256：`8e6eaac235475c3dd70db1279d90905cc36089299bb2b7f1a5840bcbd4e01bf3`。本轮未自动执行安装程序，未发布 Release。
