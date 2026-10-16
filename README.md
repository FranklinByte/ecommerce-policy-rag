# 面向电商售后的版本感知 Hybrid RAG 政策检索与证据问答系统

用于客服辅助的可运行 RAG 项目：中文 BM25、真实 BGE Embedding、Qdrant、RRF Hybrid、真实 CrossEncoder 重排、版本/日期过滤、chunk 级引用和无证据拒答。没有 LangGraph、多 Agent、MCP，也没有虚构的订单或支付接口。

**边界先读：**默认回答是可追溯的本地抽取式说明，不是付费 LLM 的自由生成。7 份真实政策事实摘要、4 份标记为 synthetic 的规则、72 条 AI 辅助固定查询，不能宣称为独立人工金标、线上客服数据或法律判断系统。真实页面适用日期未知时不伪造日期。

2026-10-16 维护：可选 LLM 输出改为逐句检查引用，防止一句带引用、后续无引用陈述混过校验；当前 67 项测试通过。引用格式检查不等于自动证明语义正确。当前代码验证见 [维护记录](docs/validation.md#2026-10-16-维护验证)，9 月的完整检索评测与原始 freeze.json 保留为历史基线。

## 启动

建议 Python **3.12**、PowerShell 7，CPU 4 核以上、至少 8 GB 可用内存；首次依赖/权重下载需要联网和数 GB 磁盘空间。真实 BGE 模型不需要付费 Key。

在本项目目录运行：

```powershell
pwsh -NoProfile -File scripts/start.ps1
```

自动创建虚拟环境、按 `uv.lock` 安装依赖、下载固定 commit 的两个模型、建立两种索引，然后打开服务。访问 <http://127.0.0.1:8010>；API 文档 <http://127.0.0.1:8010/docs>。端口占用时使用 `-Port 8020`，不会关闭别的项目服务。按 Ctrl+C 停止本次进程。

Linux/macOS：

```sh
uv sync --frozen --extra dev
uv run policy-rag download-models
uv run policy-rag index
uv run policy-rag serve --port 8010
```

首次下载失败会显式报错；不能用随机向量代替成功。模型缓存准备好后可设 `HF_HUB_OFFLINE=1` 和 `TRANSFORMERS_OFFLINE=1`，离线运行索引/评测。

## Docker

```powershell
docker compose up -d --build
docker compose ps
docker compose logs --tail 30 app
```

访问 <http://127.0.0.1:8011>。Compose 使用独立 Qdrant Server 和持久化模型/索引卷；Qdrant 不暴露宿主端口，应用以 UID 10001 运行。首次启动会下载 Embedding 并构建索引，第一次 Rerank 请求仍需加载/下载重排模型。`/ready` 检查索引和向量 collection，不保证所有模型已预热。国内网络无法连接模型源时应先解决合法的下载/缓存访问，不能把健康检查成功等同于重排已经测试。

停止但保留数据：`docker compose down`。不要随意使用 `down -v`。本地模式使用 Qdrant Local，单进程独占索引目录；索引/评测时先停止占用相同目录的本地服务，Compose 有独立目录，不受影响。

## 演示问题

| 问题 | 过滤条件 | 观察点 |
|---|---|---|
| AM115 有线耳机保修多久？ | 华为中国、配件、不填依据日期 | 型号、90 天、各路分数、引用 |
| NEBULA-P2 激活后还能无理由退货吗？ | 星云商城、手机、依据日期 2025-06-01 | 明确 synthetic，排除 v1 |
| AppleCare+ v2.4 覆盖哪些设备，和标准保修是什么关系？ | Apple 中国、版本 v2.4 | 版本精准过滤，原 PDF URL |
| 帮我查订单 998877 的物流和退款进度 | 不限、不填依据日期 | 无业务接口，无证据拒答 |

页面显示候选片段、BM25/Dense/RRF/Rerank 分数、重排前后名次和最终引用。完整片段可在候选文本区域滚动查看，完整响应也可通过 API 获取。

## CLI 与 API

```powershell
.venv/Scripts/python.exe -m policy_rag.cli verify-corpus
.venv/Scripts/python.exe -m policy_rag.cli index --strategy both
.venv/Scripts/python.exe -m policy_rag.cli query "AM115 耳机保修多久" --platform huawei_cn --mode hybrid_rerank
.venv/Scripts/python.exe -m policy_rag.cli eval eval-results/my-new-run
.venv/Scripts/python.exe scripts/validate.py
```

`eval` 的输出目录为位置参数，必须新建或为空，防止覆盖原始结果。`--config data/eval/experiment.yaml` 可指定实验配置；改变分块参数必须同步环境配置并重建索引。`index --force` 发布新版本，不删除旧版。

`POST /api/v1/query` 返回答案与轨迹；`POST /api/v1/retrieve` 只检索；`GET /health` 返回进程/索引状态；`GET /ready` 返回向量服务就绪状态。输入示例：

```json
{
  "question": "AM115 有线耳机保修多久？",
  "mode": "hybrid_rerank",
  "top_k": 5,
  "filters": {"platform": "huawei_cn", "product_category": "accessory"},
  "context": {"model": "AM115", "request_type": "维修", "opened": true},
  "generate": true
}
```

响应含 `requested_mode/effective_mode/degraded/degradation_reasons`、`index_version`、候选分数、`answer.citations`、缺失条件和拒答原因。矛盾的 filters/context 返回 422。并发模型任务返回 429；请求超时返回 504，后台计算结束前不会放开单任务锁。模型或向量服务故障回退 BM25，重排故障回退 Hybrid，并且必须显示降级。

可选提供商读取 `POLICY_RAG_LLM_PROVIDER/LLM_BASE_URL/LLM_MODEL/LLM_API_KEY`。完整变量名都带 `POLICY_RAG_` 前缀，参见 `.env.example`。密钥仅通过环境或被忽略的 `.env` 读取，不写入日志。`eval ... --provider` 才请求提供商评测；会将候选政策文本发送给配置的服务，不能加入敏感订单资料。引用 ID 校验不等于事实蕴含校验。

## 实验与工程证据

- [冻结实验报告](eval-results/frozen-2026-09-06/report.md)：2 种分块 x 4 种检索，共 576 次查询；每组分别保存 retrieval/generation JSON、CSV、失败记录。
- [固定查询](data/eval/queries.jsonl) 与 [实验配置](data/eval/experiment.yaml)：文档级 Recall@1/3/5、MRR@5、nDCG@5；生成部分记录文档引用 Precision/Recall、无答案拒答、可回答接受率、覆盖率和延迟。
- [验证记录](docs/validation.md)：本地测试、类型、Lint、覆盖率、浏览器和 Docker 的实际证据；不等同于 GitHub 云端 CI 通过。
- [局限与失败分析](docs/limitations-and-results.md)：不隐藏重排延迟、拒答漏答以及小语料下 Hybrid 不一定优于 BM25 的结果。

## 文档导航

- [架构与完整请求流程](docs/architecture.md)
- [来源、许可和日期语义](docs/data-sources.md)
- [五个开源项目复用决策](docs/reuse-decisions.md)
- [第三方声明](THIRD_PARTY.md)
- [代码地图与面试追问](docs/code-map.md)

代码测试中的 FakeEmbedder/FakeReranker 只用于隔离工程行为，临时测试结果不混入真实模型评测。可执行代码、锁文件、语料、固定集和原始结果共同构成冻结交付；个人学习和后续改动建议另建实验输出目录比较。
