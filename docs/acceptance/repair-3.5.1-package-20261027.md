# Scriptorium 3.5.1 Windows 打包与推送记录

日期：2026-10-27（Asia/Shanghai）。用户明确授权打包并推送修改。

## 构建输入

- 代码基线：`74cd7e2096f9da6e1ea0224f4c14ef266902c1d6` 加本轮预算生命周期、决定卡与可读性修复。
- 应用、Python 服务、前端与 Rust 程序版本统一为 `3.5.1`。
- 构建代码摘要：`cae4b39a0eb95d2b22a9073b58d596e57675aba7cde32b84f197c2f3e509c414`（351 个代码文件）。
- 前端先执行 `build:tauri`，随后冻结 `web/dist` 供 PyInstaller 和 Tauri 使用；打包期间不改动代码和静态产物。
- 修缮验证见 [个人工作台修缮记录](personal-repair-20261027.md)：39 项后端回归、最后 4 项预算复测、12 项前端单元以及局部浏览器验证。它们不是新增全量回归记录。

## 打包结果

Windows 当前用户 NSIS：`src-tauri/target/release/bundle/nsis/Scriptorium Agent_3.5.1_x64-setup.exe`。

- 大小：141,718,908 字节（135.15 MiB）。
- 安装包 SHA-256：`af397ce1e1a87fa10b54ffe3d3a492f0693494f76a540885d521529d4bcc83f4`。
- 已测后端、架构副本及包内提取后端 SHA-256 均为 `7512832f2b7cd18fd488f198ecd8b7b3ae72c394ac7ba9eaabff5238bfc5de4b`。
- 桌面程序版本 `3.5.1`；安装包只提取检查，没有执行安装。

包内 API/Worker 检查通过：服务版本、research_0007 独立迁移、文本导入、问候、时间线快照、阅读窗口、来源/品牌接口、Trafilatura 诊断，以及固定版本 DOCX 导出（10,633 字节）。AUTO 使用合法的 1 万 token 预算与较长合成材料，进入阶段成果后追加额度，同回合完成报告；原内容块身份保留。测试付费调用为 0。

第一次预算测试夹具使用 1,000 token，低于接口最低值 10,000，被 422 正确拒绝；调整夹具后在第二个独立目标库重新验证通过。这是测试输入修正，没有放宽产品校验或重新修改构建代码。

证据：[散列](evidence-20261027-package351/repair351-candidate-hashes.json)、[源码摘要](evidence-20261027-package351/repair351-source-digest.json)、[前端构建](evidence-20261027-package351/repair351-frontend-build.log)、[后端打包](evidence-20261027-package351/repair351-sidecar-build.log)、[NSIS 构建](evidence-20261027-package351/repair351-installer-build.log)、[包内容](evidence-20261027-package351/repair351-installer-contents.log)、[包内核验](evidence-20261027-package351/repair351-packaged-smoke.json)。

## 交付边界

安装包在本机生成，不执行安装或打开桌面 GUI；不迁移实际用户库。包内服务检查使用独立 PostgreSQL 数据库和演示提供者，没有付费模型调用。没有重新执行 ES/S3、完整安装矩阵或学术质量评分。

源码、测试、文档与核验记录提交到 `origin/main`；安装包保存在本机，不将大体积二进制提交到 Git 仓库，也不创建 GitHub Release。推送后 CI 状态单独记录，未结束的 CI 不表述为通过。
