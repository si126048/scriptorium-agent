# 研究服务架构决策记录

日期：2026-10-24。状态：已实施的开发版决策，不代表生产发布。

## ADR-01：PostgreSQL 与旧运行时隔离

新增独立 `hermeneut.research` 服务和 `/api/v2`。数据库采用 SQLAlchemy 2 Core、psycopg 3、Alembic。稳定身份和关联使用列与外键；版本化解释载荷使用 JSONB。普通材料不依赖参与者。

旧 API、CLI、SQLite 和画像模块保持原路径。新版默认界面可切回旧功能；研究服务器本身不隐式打开旧数据库。旧 API 不在首版全部转接 PostgreSQL。

现有调用链：旧 API／CLI → rag 导入 → Store 的 documents／spans → Workflow／DialecticalWorkflow → 审核及导出；PageIndex 使用独立 DocumentStore → doc_store／doc_pages／FTS。访谈经 InterviewManager 进入原分析流程，Persona 经 TopoStyle service 管理自己的对话表。新链路：研究界面 → v2 → 原件登记与 Job → Worker → TEI／Segment／Anchor → 方法对象与 Records → outbox／ES → 论证与导出。

## ADR-02：Elasticsearch 是可重建投影

事务 outbox 驱动段落索引；以材料修订号限制旧事件覆盖。搜索按项目过滤，并从 PostgreSQL 回查材料可用状态。不返回未授权数量聚合。故障返回 503，不假装没有命中。

首版使用 CJK 分析器和短语查询，保留原词字段；学术词典、复杂语义检索和按时期筛选尚未完成。重建使用新索引和 alias 切换，旧索引不自动删除。

## ADR-03：原件和文本版本不可变

文件对象采用完整 SHA-256、临时文件、fsync 与原子替换；路径只接受严格的内容键。FileObjects 是首版实现；ObjectStore 协议留出 S3 接口，未实现 S3 适配器。

数据库只登记已存在且通过散列校验的对象。登记失败留下可清理孤儿，gc 至少保留一小时，默认 24 小时，先预览再 apply。备份不会因在线撤回而自动改写，必须另行执行备份保留与销毁政策。

## ADR-04：TEI 子集与 reading.v1

保留原件，生成或接收有限 TEI P5 子集，使用 Relax NG 加引用检查。禁用 DTD、外部实体及网络解析。不支持的结构明确拒绝，原件仍保留；未实现通用 TEI 无损转换器、完整 ODD 工具链或 Schematron。

reading.v1 按块保留内联全部文本，包括 note 及 choice 的子项，既不折叠空白，也不自动选择校勘读法；因此它是明确版本的投影，而非最终校勘文本。位置使用 Unicode code point 半开范围，前端从 UTF-16 转换。

## ADR-05：数据库任务队列

Worker 使用行锁、SKIP LOCKED、租约和独占 token；心跳续租，失去所有权后不能提交。失败显示错误码，可显式重试；超期的处理中任务可重新领取。取消后不启动新工作，无法承诺已发出的模型请求立即终止。

SSE 使用已保存事件 ID 恢复。任务端点不依靠 Web 请求存活。首版 Worker 为顺序执行，一个任务中的模型分析为一次受限调用；没有实现自动多轮研究调度。

## ADR-06：方法、视角与对象分开

思想构境、内在批判、视差是三种独立协议，保存来源、模板、范围、结果模式与证据。复用 Qwen 传输；demo 显式选择，真实服务失败不降级到 demo。模型输出经过结构与原文校验。

内在困难要求立场、尺度与证据；转化要求保留、否定及理由。裂隙候选要求位置、对象位移、已检查原因、反驳条件和证据。没有生成最终真理或“必然综合”的状态。

## ADR-07：个人研究优先，保留服务边界

默认单用户，由服务端配置固定身份，客户端不能传用户头冒充。保留项目成员和 owner/editor/reader 检查；远程部署必须设置研究密钥。首版不提供多人登录与成员邀请，不能作为团队系统直接对公网开放。

Tauri 可保存外部研究服务模式，下次启动不启动旧 sidecar；清除模式后恢复旧启动方式。数据库服务不打入桌面安装包。Compose 只暴露本机 API，内部数据库不对宿主开放。

## ADR-08：一致性快照迁移与兼容档案

SQLite 以只读连接和 backup API 取得包含已提交 WAL 的一致视图。旧实体按来源、表、键保存，批量 500 条，保留 legacy ID 映射。聊天历史通过浏览器导出导入，不扫描浏览器私有存储。

旧分析、访谈与 Persona 首先以只读兼容档案保留；尚未把全部旧业务逻辑改写到新数据库。不确定归属进入“归属待确认”项目，原件缺失时使用旧正文，明确缺失状态。失效同意项目采用保守阻断，不复活敏感内容；混合项目需要研究者重新整理。

旧偏移必须经原文核验才能复用；否则只接受唯一精确匹配。迁移重跑不能覆盖已脱敏或撤回的历史。正式切换必须先停止旧端写入，保留快照与报告，不双写。

## 验证版本

实际验证：Python 3.12、PostgreSQL 17.6、Elasticsearch 8.19.3、SQLAlchemy 2.0.55、psycopg 3.3.6、Alembic 1.20.1、lxml 6.1.3。研究新增依赖记录于 requirements-research.lock。

这些是复现本轮测试的版本，不声明是各组件最新安全版本；部署更新应重新验证兼容性。

## 官方参考

- [SQLAlchemy PostgreSQL／psycopg](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)
- [PostgreSQL SELECT 锁定](https://www.postgresql.org/docs/current/sql-select.html)
- [Elasticsearch Python 客户端](https://www.elastic.co/docs/reference/elasticsearch/clients/python/connecting)
- [TEI 原始材料](https://tei-c.org/release/doc/tei-p5-doc/en/html/PH.html)

Misaka 相关既有署名和许可证保留；本轮没有复制新的上游源码。
