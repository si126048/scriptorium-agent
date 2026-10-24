# 模型服务商与密钥保存（providers.v1）实施与验收记录

记录日期：2026-10-24  
范围：工作台模型密钥保存失败、仅支持通义千问的问题  
状态：**已实现并通过自动化与浏览器验证；未调用真实服务商。**

## 1. 问题与原因

- **前端保存失败**：旧接口 `PUT /api/v2/system/model` 只接受 `{key}`，且 `save_key` 要求 `SCRIPTORIUM_LOCAL_RUNTIME_ROOT`（仅桌面托管安装设置）并写 Windows 凭据；源码 `serve` 启动时该变量为空，返回 409 `MODEL_KEY_MANAGED_BY_SERVER_ENVIRONMENT`。前端仍显示“Qwen 密钥已保存”，实际未写入。
- **只支持 Qwen**：`GET/PUT /api/v2/system/model` 硬编码 `provider='qwen'`；方法、提问、理论比较等统一走 `QwenProvider()`，基址固定 DashScope。

## 2. 现在的行为

| 能力 | 说明 |
|---|---|
| 服务商目录 | 通义千问、DeepSeek、OpenAI、Moonshot、智谱 GLM、本机 Ollama、自定义 OpenAI 兼容端点 |
| 保存并启用 | `PUT /api/v2/system/model` 接受 `provider`、`base_url`、`model`、`key`，保存后立即生效 |
| 密钥位置 | Windows 默认系统凭据（Credential Manager）；非 Windows 或 `SCRIPTORIUM_KEY_STORAGE=file` 时写私有文件（0600）；接口只返回“已配置／来源” |
| 环境变量后备 | `DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`MOONSHOT_API_KEY`、`ZHIPU_API_KEY`、`SCRIPTORIUM_MODEL_API_KEY`；保存值优先 |
| 状态与来源 | `GET /api/v2/system/model` 返回目录、当前服务商、`configured`、`ready`、`source`（credential-store／private-file／environment／unset）、`storage` |
| 清除与探测 | `DELETE /api/v2/system/model` 清除密钥；`POST /api/v2/system/model/test` 只列出模型，不发送材料、不回显密钥 |
| 旧运行时 | CLI／ACP／MCP 在 `QwenProvider()` 无显式参数时跟随当前服务商；显式参数保持原行为 |
| 前端 | “设置与档案 → 研究模型”：服务商、接口地址、模型、密钥、保存并启用、清除、测试连接；密钥输入不回显 |

接口与实现：`scriptorium/research/providers.py`、`api.py`（`/api/v2/system/model`）、`capabilities.py`、`methods.py`、`model_credentials.py`（兼容外观）、`scriptorium/llm.py`（默认构造跟随注册表）、`web/src/features/workspace/components/ModelProviderForm.tsx`。

## 3. 已验证证据

自动化 `tests/test_research_providers.py`（10 项）：

| 用例 | 断言 |
|---|---|
| 目录与默认 | 7 个服务商、默认通义千问、`editable=true`、未配置 |
| 保存密钥 | 只写私有文件、响应与状态不含密钥、来源为 `private-file` |
| 切换与覆盖 | 切到 DeepSeek 后基址／模型生效，provider 对象使用保存值 |
| 环境变量后备 | `DASHSCOPE_API_KEY` 保持旧行为；保存值优先于环境变量 |
| 缺密钥 | `MODEL_NOT_CONFIGURED`；删除后同样失败 |
| 自定义端点 | 无基址报 `PROVIDER_BASE_URL_REQUIRED` |
| 非法密钥 | 空值、含空格、未知服务商分别报错 |
| HTTP 接口 | 保存切换、状态隐藏密钥、清除、探测缺密钥返回错误码 |
| 旧运行时跟随 | `QwenProvider()` 使用当前服务商与模型 |
| 旧环境兼容 | 仅设 `DASHSCOPE_API_KEY` + `LACAN_MODEL` 时仍为 DashScope + `qwen-max` |

浏览器 `scripts/browser_acceptance.py`（22 项全部通过）新增：

- `MODEL-01` 在设置面板选择 DeepSeek、输入密钥并保存，页面提示“立即生效”；
- `MODEL-02` 密钥不在页面回显，状态显示“已配置（私有文件）”。

截图：`output/acceptance-browser/06b-model-provider.png`。全量回归：**371 passed / 0 skipped**（`output/providers-final-suite.log`），其中新增 provider 测试 10 项。

## 4. 与 Misaka-Agent 的关系

沿用其“服务商注册表 + 当前服务商 + 每服务商密钥与模型”的组织方式（DeepSeek／OpenAI／Ollama 等可直接切换），没有复制其代码、`auth.json` 格式或品牌资产。查阅版本与许可证见 [参考来源](agent-experience-references.md)。

## 5. 边界

- **没有调用任何真实服务商**：测试用替身断言配置与请求参数；`测试连接` 的失败路径已验证，成功路径需在配置真实密钥后确认。
- 只有 OpenAI 兼容协议（`/chat/completions`、`/models`）；Anthropic、Gemini 原生协议不在本次范围。
- 密钥保存在本机；多用户服务器部署仍应使用环境变量或外部密钥管理，不把本机密钥当作共享凭据。
- 旧版本地运行时（CLI／ACP／MCP）默认跟随当前服务商；若未切换，仍等价于原来的 DashScope 行为。
- 服务商质量、限额与失败重试策略未做跨服务商对比评测。

## 6. 桌面“一直在读取模型设置”修复（2026-10-24 深夜）

原因：桌面桥 `get_research_connection` 在未保存服务地址时会启动打包后端执行 `local-runtime connection`；未安装本机运行时时该调用很慢或失败，前端旧逻辑最多重试 60 次、每次 1 秒，且每次都会再启一个后端进程，界面因此长时间停在“正在读取模型设置…”。

修复：

- 前端只询问一次桌面地址（2.5 秒超时），失败即回退 `http://127.0.0.1:8010` 并记录可见提示；所有请求增加 30 秒超时；模型设置读取 8 秒超时并提供“重试”。
- 桌面命令 `get_research_connection` 增加 8 秒超时；启动时的 `local-runtime ensure` 增加 180 秒上限，失败只写日志。
- 版本升为 3.1.1 并重建安装包（NSIS 123.96 MiB、MSI 125.25 MiB）。

验证：

- `scripts/desktop_fallback_check.py` 3 项通过：界面可用、模型设置不再无限加载、明确提示已回退地址（截图 `output/acceptance-browser/11-desktop-ipc-fallback.png`）。
- 主浏览器套件 22 项通过；全量测试见 `output/post-desktop-fix-suite.log`。
- 说明：无头浏览器累计标签页会耗尽同源连接而让首个请求排队，这是测试环境现象；用全新浏览器实例复测后三项均通过。
