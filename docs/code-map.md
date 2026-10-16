# 代码地图与面试追问

| 入口/模块 | 可以沿着代码回答的问题 |
|---|---|
| `models.py` | 为什么文档、chunk、候选、引用分开建模？未知生效日期怎么表示？ |
| `config.py` | 环境变量校验、SecretStr、模型 revision 与阈值在哪里固定？ |
| `corpus.py` / `sources.py` | 数据来源、下载跳转白名单、原文/摘要 hash 有何区别？ |
| `loaders.py` / `chunking.py` | 层级分块保留什么？窗口跨章节有什么代价？PDF 扫描件为何不支持？ |
| `retrieval/tokenizer.py` / `bm25.py` | 中文分词与型号切分、IDF、长度归一化如何影响结果？ |
| `retrieval/embedding.py` / `dense.py` | Query instruction、512 维归一化向量、余弦、payload 日期过滤在哪里？ |
| `retrieval/service.py` | 四种模式怎样共用同一数据？RRF 的 k 代表什么？排序变更怎么追踪？ |
| `retrieval/reranker.py` | Bi-Encoder 和 Cross-Encoder 有什么计算代价？sigmoid 能不能称置信概率？ |
| `indexing.py` | 内容寻址、不可变构建、原子替换、失败回滚和模型不匹配怎么处理？ |
| `generation.py` / `service.py` | 证据阈值、版本冲突、抽取式生成与真实 LLM 的能力边界是什么？ |
| `evaluation.py` / `data/eval/` | 手算 Recall、MRR、nDCG；拒答与引用分别评什么？标签是不是人审？ |
| `api.py` / `static/` | 请求超时为何不能杀掉推理线程？429/503/504 如何区别？ |
| `tests/` / `compose.yaml` | Test doubles 验证工程逻辑还是模型质量？Local 与 Server 各验证了什么？ |

## 面试追问清单

1. 为什么这是 Hybrid 而不是关键词搜索？给出真实向量模型、Qdrant 数据和四组原始报告。
2. 精确型号为什么可能 BM25 更好，口语为何可能 Dense 更好？拿具体失败案例，不泛泛讲优势。
3. 为什么不直接将 BM25 和余弦相加？RRF 丢掉了哪些原始分值信息？
4. Reranker 带来的 Recall/MRR 改善有多大，CPU p95 增加多少，为什么不总是开启？
5. 只召回一个相关文档但没取到正确条款，会被当前文档级指标漏掉吗？会，如何升级标注？
6. 数据仅 11 份摘要却 Recall@5 很高，能证明大规模电商泛化吗？不能。
7. 72 条查询是谁标的？是否独立人审？怎样设计后续盲标和真实客服日志测试？
8. 无答案拒答高时可回答接受率是否下降？哪个指标阻止“全部拒答”刷高分？
9. 为什么不把抓取日期当生效日期？旧版合同与新版条款如何同时有效？
10. 星云规则是否真实？版本处理被验证的范围是什么？
11. 如何发现模型换了但索引没重建？怎样避免半成品覆盖可用索引？
12. Embedding、Qdrant、Reranker、生成模型分别失败，用户看到什么？
13. 引用 ID 合法是否代表回答正确？没有 LLM Key 时实际运行的是什么生成方式？
14. Qdrant Local 是否测了服务端 HNSW 大规模性能？没有，Server 仅做了小语料功能验收。
15. HTML/PDF 的复杂表格、图片、扫描件、含脚本页面如何处理？哪些必须明确拒绝？
16. 第三方代码、模型许可证、政策再分发授权分别是什么，原创边界在哪里？
