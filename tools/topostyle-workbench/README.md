# TopoStyle 独立工作台

2026-10-23 从 `D:\ai\TopoStyle` 整体归入本目录，统一由 Scriptorium 管理。源码、测试、示例、产物和本地环境均保留。

Scriptorium 产品功能位于 `scriptorium/topostyle/`，使用项目、参与者、授权、SQLite 和 Ollama。本工作台提供另一套离线语料特征提取 CLI，包含 TF-IDF、持久同调和共现图；两者实现有差异，因此保留为子项目，没有覆盖或替换产品模块。

在本目录执行：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.venv\Scripts\python.exe -m topostyle.cli --help
.\.venv\Scripts\python.exe -m topostyle.cli extract <语料目录> --output artifacts
.\.venv\Scripts\python.exe -m pytest tests -q
```

迁移后使用 `python -m`，避免旧环境启动器可能保留的原目录路径。重建环境时使用本目录的 `pyproject.toml`；本次未安装依赖或修改系统 Python。

原始设计见 [实现计划](docs/implementation-plan.md)。
