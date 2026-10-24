# TopoStyle 实施计划

## 已完成：阶段 1A（可计算基线）

- 项目骨架、虚拟环境和 CLI。
- 语料清洗、段落/句子切分和 segment 元数据。
- 可复现的 TF-IDF 字符 n-gram fallback embedding；未来接入 SentenceTransformer 时保留相同接口。
- 余弦距离矩阵、Ripser H0/H1/H2 持续图、持久特征向量、词汇共现图。
- `.npy`、`.csv`、GraphML、JSON 输出和基础测试。

## 下一步

1. **阶段 1B：真实 embedding 与评估**：接入 `all-MiniLM-L6-v2` 可选后端，补齐 Betti 曲线、Wasserstein 距离和同作者/异作者验证报告。
2. **阶段 2：多源表征**：人格四元组 JSONL、StyleVector 抽象接口、共享 PCA 拟合与保存。
3. **阶段 3：TUI**：Textual 单 Persona 对话、provider 抽象和流式渲染；无 API key 时提供 mock provider。
4. **阶段 4–6**：Persona/SQLite、训练任务、拓扑监控和闭环 alpha 扫描。

每阶段先完成离线可测试模块，再接入外部模型；所有生成内容默认标记 AI，支持删除语料与产物。
