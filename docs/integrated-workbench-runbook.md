# Scriptorium 集成工作台运行说明

本轮基于 3.1.1 增量修缮；旧 README、tools 及旧数据库保留。数据库目标修订为 `research_0005`，不能让旧程序直接访问升级后的库。

## Windows 个人模式

当前用户 NSIS 为候选交付方式，已有外部服务连接方式继续保留。后台安装调用 `local-runtime install`，固定 PostgreSQL 17.6、Elasticsearch 8.19.3；新增 Pandoc 3.12.1 从官方来源下载并校验归档及可执行文件散列。断网首次安装不能声称完成导出运行时部署，恢复网络后重试。

数据、对象、日志与运行时均使用当前用户目录；Windows 系统凭据保存本机服务凭证。设置中的临时 API 密钥仅留在当前页面内存；桌面连接通过既有 IPC 配置，不写入会话或项目。关闭窗口后由既有后台管理器继续执行任务。安装不自动迁移旧研究数据。

源码运行使用 `pip install -c requirements-research.lock '.[research]'`，准备隔离 PostgreSQL、ES 后设置 `SCRIPTORIUM_DATABASE_URL`、`SCRIPTORIUM_OBJECT_ROOT`、`SCRIPTORIUM_ELASTICSEARCH_URL`。先运行 `scriptorium-research init-db`，再分别启动 `scriptorium-research serve --port 8010` 和 `scriptorium-research worker`。浏览器访问 API 相同地址。

## Linux 课题组

提供独立 `compose.team.yml`；不要与个人 `compose.research.yml` 叠加。需要 Linux Docker Compose、两个 DNS 主机名及可签发 HTTPS 证书的 80/443 端口。当前开发机没有执行 Docker，不把配置校验视为部署验收。

1. 复制 `deploy/team/team.env.example` 到部署机的私有 `.env.team`，替换域名和三个独立随机密码。数据库密码使用 URL-safe 字符。不要提交此文件。
2. 执行 `docker compose --env-file .env.team -f compose.team.yml up -d --build`。服务只发布反向代理的 80/443；PostgreSQL、ES、Keycloak 的内部端口不发布到宿主机。
3. 在登录域名的 Keycloak 管理台进入 `scriptorium` realm，创建用户并设定首次登录流程。默认禁止用户自助注册；公共客户端使用 authorization code + PKCE S256，不使用客户端秘密或密码授权。
4. 用户在应用登录并创建项目，自动成为该项目负责人。已有项目的负责人在“项目与成员”面板添加成员，使用对方 `/api/v2/auth/session` 中的 `user_id`。角色为负责人、研究者、评议者和只读成员。
5. 服务器模型配置管理员由 `SCRIPTORIUM_ADMIN_SUBJECTS` 明确指定，值是应用散列用户 ID（`oidc:…`），多个 ID 以逗号分隔。它与项目负责人角色分开。修改后重建 API/Worker 容器。普通成员不能改模型地址或密钥。
6. 团队模式默认禁止外部模型处理；项目负责人在项目面板指定服务商主机名、材料及文本版本、用途说明和累计预算。敏感材料不能外发，新上传的文本版本需要补充授权。用途当前为审计说明，不是自动判定研究内容的分类器。

Keycloak 26.4.7、Caddy 2.10.2 固定为本候选配置版本，PostgreSQL/ES 沿用已验证版本；不宣称这些是当前最新版本。Keycloak 反向代理使用固定公开 hostname、HTTP 内部入口及 xforwarded，代理不转发客户端伪造的外部主机头。

Realm 导入变量使用 Keycloak 原生 `${SCRIPTORIUM_PUBLIC_URL}` 占位符；已存在的 realm 在启动时不会被覆盖，变更回调地址应通过管理台修改。参见 [Realm 导入](https://www.keycloak.org/server/importExport)。

身份来源：[Keycloak hostname](https://www.keycloak.org/server/hostname)、[反向代理配置](https://www.keycloak.org/server/reverseproxy)、[26.4.7 发布说明](https://www.keycloak.org/docs/26.4.7/release_notes/index.html)、[Caddy 2.10.2](https://github.com/caddyserver/caddy/releases/tag/v2.10.2)。

## 写作、建议与导出

报告默认阅读，文稿默认进入可视化编辑。编辑源为 JSON，Markdown 为派生文本。章节独立修订；保存采用修订检查，冲突保留本机草稿，不覆盖远端。自动保存约 1.2 秒；立即保存可手动触发。历史版本可比较并恢复为新修订。

“建议修改”只创建候选内容，接受后才写入正式稿。演示结果始终标为演示；真实模式使用当前管理员配置的模型，相关调用计入账本。不要把演示内容当作正式学术结论。

导出 DOCX / Markdown / HTML 时在后台使用固定 Pandoc 和内置中文脚注、英文脚注、作者年份 CSL。DOCX 脚注及书目来自文稿引用节点与材料书目信息。原文锚点可定位与论点获得支持是不同状态；本轮没有组织学术质量评分。JSON/TEI 沿用项目档案导出。

## 升级、备份与恢复

正式升级前停止本产品 API/Worker 写入，使用已有逻辑备份：`scriptorium-research backup <新的备份目录>`。备份包含表、对象散列、调用账本与导出对象；应用配置的密钥不随研究包导出。恢复只允许空的独立目标库：先设置目标数据库/对象目录，运行 `init-db`，再运行 `restore <备份目录>`。如源数据发生撤回，提供 `--withdrawal-ledger`，不能靠恢复绕过撤回。

团队身份服务器的数据库、HTTPS 证书与私有模型配置应单独按部署平台备份。应用备份包含个人工作区及会话身份，应由管理员保存，不能作为公开项目包分发。迁移只在隔离库预演，正式切换仍需停写、快照、异常确认和新版新增内容保全。

本轮应用集成检查已实际恢复过一次隔离备份；Linux 整套服务、真实 Keycloak、干净 Windows 用户安装和卸载仍以验收记录为准。
