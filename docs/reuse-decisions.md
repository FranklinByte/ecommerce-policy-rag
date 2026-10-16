# 开源复用决策

核验时间：2026-09-06。来源为各仓库根 README、许可证、官方实现或文档，以及 GitHub API 的默认分支最新提交。`pushed_at` 包括其他分支活动，不等于默认分支最后提交；星数不作为质量证据。

| 项目 | 许可证与维护快照 | 解析、检索、重排 | 引用与评测 | 本项目取舍 |
|---|---|---|---|---|
| [Kotaemon](https://github.com/Cinnamon/kotaemon) | Apache-2.0；默认分支 `9ad3e4e49aa3`，2026-05-30；最近 push 2026-07-14 | 多格式 Loader、向量/文本/Hybrid；可配置 Reranker | 引用可视化、检索片段展示；不是固定电商基准 | 借鉴检索与证据展示分层，自己实现轻量 UI；不引入 ktem 产品框架 |
| [RAGFlow](https://github.com/infiniflow/ragflow) | Apache-2.0；`0c28d59ea1d3`，2026-09-05；活跃维护 | 深度解析与模板分块；关键词与向量加权组合；模型重排 | 文档定位、引用、检索测试与评测能力 | 借鉴先检查召回再检查回答的方法；不移植分布式解析、Agent 或管理后台 |
| [Onyx](https://github.com/onyx-dot-app/onyx) | 非 `ee` 代码 MIT；`ee` 为 Onyx Enterprise License；`06aa2b09cc4a`，2026-09-04 | 多源连接器、关键词与向量索引、独立模型服务与重排 | 来源引用、搜索结果；官方 README 的新基准当时尚待发布 | 借鉴元数据/文档身份/检索服务边界；不复制 EE、权限平台、连接器集群 |
| [qdrant-rag-eval](https://github.com/qdrant/qdrant-rag-eval) | 根目录未发现 LICENSE，API license=null；`a101fac6bbf9`，2024-10-08；最后 push 2025-04-25 | 教程和 workshop 集合，不是独立生产级检索服务 | Qdrant/Ragas 评测参考材料 | 只参考实验分解思路；无明确许可证，不复制 notebook 或代码 |
| [Open RAG Eval](https://github.com/vectara/open-rag-eval) | Apache-2.0；默认分支 dev，`9803c35bc1cf`，2026-06-02 | 通过 connectors 读取既有 RAG 输出，新增 chunk 对照层；不替代业务检索器 | TREC-RAG 风格指标、UMBRELA/AutoNuggetizer、逐查询 JSON/CSV；部分指标依赖 LLM/HHEM | 借鉴逐查询中间产物、检索/生成分离；固定 qrels 指标自行实现，付费 Judge 不作为核心依赖 |

## 原始证据入口

- [Kotaemon 许可证](https://github.com/Cinnamon/kotaemon/blob/main/LICENSE.txt)、[文件检索流水线](https://github.com/Cinnamon/kotaemon/blob/main/libs/ktem/ktem/index/file/pipelines.py)、[回答与引用流程](https://github.com/Cinnamon/kotaemon/blob/main/libs/ktem/ktem/reasoning/simple.py)。
- [RAGFlow 许可证](https://github.com/infiniflow/ragflow/blob/main/LICENSE)、[检索测试说明](https://github.com/infiniflow/ragflow/blob/main/docs/guides/dataset/run_retrieval_test.md)。
- [Onyx 分区许可证](https://github.com/onyx-dot-app/onyx/blob/main/LICENSE)、[官方文档](https://docs.onyx.app)。不将社区和商业部分统一标为 MIT。
- [Qdrant 评测参考根目录](https://github.com/qdrant/qdrant-rag-eval)、[Qdrant Python 客户端](https://github.com/qdrant/qdrant-client)。两者是不同仓库，前者许可未知不影响合法使用 Apache-2.0 客户端。
- [Open RAG Eval README](https://github.com/vectara/open-rag-eval)、[指标说明](https://github.com/vectara/open-rag-eval/blob/dev/METRICS.md)。

## 最终模块选择

| 模块 | 选择 | 原因与代价 |
|---|---|---|
| 文档契约 | Pydantic 自有模型 | doc/version/hash/section 显式可测，不隐藏在框架 metadata 字典 |
| HTML/PDF/Markdown | BeautifulSoup、pypdf、小型 Markdown 标题解析器 | 当前文本型政策足够；扫描件 OCR、跨页复杂表格不宣称支持 |
| 稀疏检索 | Jieba＋精确标识符＋中文字二元组；BM25 公式自有实现 | 中文口语与型号兼顾；当前小语料按过滤子集计算 IDF，非大规模倒排引擎 |
| Dense | BGE-small-zh-v1.5＋SentenceTransformers | 真实中文 Embedding、512 维；固定模型 commit；不需要付费 Key |
| 向量索引 | Qdrant Local / Qdrant Server | 未换用其他向量库；本地模式简化演示，Compose 验证服务端 payload 过滤。Local 模式主要是精确搜索，不能宣传为大规模 HNSW 性能验证 |
| 融合 | RRF，k=60 | 对不同量纲不直接加分，保留每路分数与排名；阈值不能取归一化最高 RRF=1 作为相关概率 |
| 重排 | BGE-reranker-base CrossEncoder | 输入 query-document 对；显式 Identity 激活取得 logits，再做一次 sigmoid。输出是排序分数，不是校准后的正确率 |
| 回答 | 抽取式默认，兼容提供商可选 | 无 Key 能回答有证据的政策，但不是自由推理 LLM；提供商失败显式回退，引用 ID 做结构校验 |
| 评测 | 固定 72 条＋8 组消融＋JSON/CSV/Markdown | 分开检索、引用、拒答、延迟；不把人工未复核的 AI 标签称为金标 |

## 原创与复用边界

业务元数据、时间过滤、分块契约、RRF、证据门控、CLI/API、UI、固定查询与评测报告由本项目 AI 辅助编写，不是上述项目的改名 fork。没有复制这五个项目的产品源代码。模型权重、解析库、向量库、Web 框架和 Lucide 图标是第三方依赖，不能宣称原创算法、训练数据或模型。

代码规模受控；不引入 LangGraph、多 Agent、MCP、订单/支付/物流伪接口。模型训练、真实客服日志、人审数据集、多租户鉴权和生产 SLA 不在当前交付范围。
