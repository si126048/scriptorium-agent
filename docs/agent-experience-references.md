# Agent 工作台参考来源与许可证记录

查阅日期：2026-10-24。下列版本为查阅时 GitHub API 返回的 main 提交，固定到提交链接。只吸收设计与架构实践，本轮没有复制这些项目的代码、提示词、品牌资产或动画素材。

| 项目 | 查阅版本 | 用途 | 许可证元数据 |
|---|---|---|---|
| [danny-avila/LibreChat](https://github.com/LibreChat-AI/LibreChat) | [f18b16baedab](https://github.com/LibreChat-AI/LibreChat/tree/f18b16baedab8eacc77c0523adfbeeff36ff8920) | 对话与文档分区、持续修订 | MIT |
| [langgenius/dify](https://github.com/langgenius/dify) | [fad500af4482](https://github.com/langgenius/dify/tree/fad500af44823491a18a11c666ffb243af7431f5) | 持久事件、阶段进度、决定卡 | NOASSERTION |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | [fee10e3d2909](https://github.com/OpenHands/OpenHands/tree/fee10e3d2909ebbf9950578575b1ee011492171e) | 客户端与服务连接分层 | MIT |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | [4c52e129eb1a](https://github.com/langchain-ai/langgraph/tree/4c52e129eb1ab69a3da58b799f67929f77d81149) | 检查点与业务对象分离；没有引入 LangGraph 引擎 | MIT |
| [Luciole-Studio/Misaka-Agent](https://github.com/Luciole-Studio/Misaka-Agent) | [3bcf7a33fb33](https://github.com/Luciole-Studio/Misaka-Agent/tree/3bcf7a33fb33109d03e368873570d0a7b402b210) | 分支、来源和未决问题组织 | Apache-2.0 |

Dify 元数据为 NOASSERTION，不据此推定可复制代码；如将来复用，需核读该提交的 LICENSE 与附加条款。其他项目的仓库元数据不能替代逐文件许可证核查。

产品与依赖文档：

- [LibreChat Artifacts](https://www.librechat.ai/docs/features/artifacts)：报告与对话分区；没有引入生成代码执行。
- [Dify base.ts](https://github.com/langgenius/dify/blob/fad500af44823491a18a11c666ffb243af7431f5/web/service/base.ts)：流式事件生命周期。
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)：业务状态与执行检查点区别。
- [Tiptap 3.x](https://tiptap.dev/docs/editor/getting-started/overview)：开源编辑核心及自定义节点。
- [Radix](https://www.radix-ui.com/primitives/docs/overview/introduction)：可访问的对话框、菜单和折叠。
- [Motion reduced motion](https://motion.dev/docs/react-use-reduced-motion)：系统减少动态效果与安静模式。

新增运行依赖以 web/package-lock.json 为精确版本依据。TanStack Query、Zustand、Radix、Motion、Tiptap 使用其开源包；许可证原文仍在对应 npm 包中，发布时随依赖清单保留。未使用 Tiptap 付费云服务。

OpenAPI 类型：当前 openapi-typescript 7.13.0 的 peer 范围只含 TypeScript 5，而项目使用 TypeScript 6，未强制安装。采用 scripts/generate-api-types.py 从 FastAPI 模式生成请求类型；验收检查生成文件是否过期。响应 DTO 仍有手工定义，后续可逐步补充 response_model。
