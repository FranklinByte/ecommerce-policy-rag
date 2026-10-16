# 第三方依赖与原创边界

本项目代码采用 MIT；这不授予任何商家政策原文、品牌标识、模型或依赖的新许可。没有复制或改名发布 Kotaemon、RAGFlow、Onyx、qdrant-rag-eval、Open RAG Eval 的产品源代码。架构参考和维护核验见 [复用决策](docs/reuse-decisions.md)。

## 直接依赖

版本固定于 `pyproject.toml`，全部传递依赖、平台条件和包文件哈希固定于 `uv.lock`。锁定保证实验可重建，不代表这些历史版本是最新或通过了安全审计。

| 依赖 | 上游许可 | 使用位置 |
|---|---|---|
| [Qdrant / qdrant-client](https://github.com/qdrant/qdrant-client) | Apache-2.0 | Local/Server 向量存储与过滤 |
| [SentenceTransformers](https://github.com/UKPLab/sentence-transformers) / [Transformers](https://github.com/huggingface/transformers) | Apache-2.0 | Embedding、CrossEncoder 真实推理 |
| [PyTorch](https://github.com/pytorch/pytorch) | BSD-style；包含第三方 notices | CPU 张量计算，不训练模型 |
| [BGE-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5) / [BGE-reranker-base](https://huggingface.co/BAAI/bge-reranker-base) | 模型卡 MIT | 下载上游权重；commit 固定，不计为自研模型 |
| [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) | MIT | HTML 文本提取 |
| [pypdf](https://github.com/py-pdf/pypdf) | BSD-3-Clause | 文本型 PDF 提取 |
| [Jieba](https://github.com/fxsjy/jieba) | MIT | 中文分词与词典 |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause | 数值计算和统计 |
| [FastAPI](https://github.com/fastapi/fastapi) / [Pydantic](https://github.com/pydantic/pydantic) / pydantic-settings | MIT | API 与数据校验 |
| [HTTPX](https://github.com/encode/httpx) / [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | HTTP 请求与服务 |
| [PyYAML](https://github.com/yaml/pyyaml) / [Typer](https://github.com/fastapi/typer) | MIT | 清单和 CLI |
| [psutil](https://github.com/giampaolo/psutil) | BSD-3-Clause | 资源统计 |
| [structlog](https://github.com/hynek/structlog) | Apache-2.0 OR MIT | JSON 日志 |
| [Tenacity](https://github.com/jd/tenacity) | Apache-2.0 | 有限传输重试 |

开发依赖：pytest/pytest-cov/respx/Mypy 及类型存根主要为 MIT，Ruff 为 MIT，Playwright 为 Apache-2.0，pypdfium2 包含 Apache-2.0/BSD 许可组合及 PDFium 第三方许可。uv 为 Apache-2.0 OR MIT。准确声明以各锁定发行包自带 LICENSE/NOTICE 为准；并未把依赖源代码扁平复制进项目。

## 前端静态分发

唯一直接随仓库分发的第三方 JavaScript 是 Lucide **0.468.0** 的 UMD 图标包，来自 `https://unpkg.com/lucide@0.468.0/dist/umd/lucide.min.js`。原文件保留上游标头；完整 ISC 与衍生 Feather MIT 声明保存在 `src/policy_rag/static/lucide.LICENSE`。UI 布局、交互、分数轨迹和样式是本项目代码，不使用品牌官方 Logo。

## 数据与自有实现

`data/policies/` 为 AI 辅助的有限事实摘要，`data/fixtures/` 为项目合成规则；商家全文只允许本地验证，不随 Git/Docker 分发。详细 URL、下载 hash 和许可状态见 [数据说明](docs/data-sources.md) 与 `data/sources.yaml`。

本项目自行实现的是业务 schema、分块组织、BM25 计算、RRF 融合、时间过滤契约、证据门控、引用映射、实验协议、API/CLI/UI 和测试。BM25/RRF 为已有算法，不宣称算法原创。BM25 来源：[Robertson & Zaragoza, 2009](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf)；RRF 来源：[Cormack et al., SIGIR 2009](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)。
