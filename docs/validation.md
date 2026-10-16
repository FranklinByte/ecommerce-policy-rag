# 交付验收与证据

## 2026-10-16 维护验证

修复可选 LLM 生成分支只要求整个字段出现一次引用的问题。现在解释、适用条件、不适用条件中的每个句子都必须在句末标注有效引用；接受中文/英文标点、引用在标点前后及小数，拒绝混入无引用后续句、借用下一行引用、孤立引用和无引用输出。原有引用 ID 白名单检查保留。无法通过校验时按原有路径返回不可用/拒答，不放行有缺口的生成结果。

这是引用完整性与格式校验，不是事实蕴含验证：一句话即便带了合法引用，也可能与原文不符。默认抽取式回答、Embedding、混合检索和 Rerank 逻辑未改变。

本次 67 项测试通过（新增 13 个参数化断句用例，并扩展生成分支集成用例）；综合覆盖率 93.73%，独立分支覆盖率 89.04%。Ruff 格式/静态检查、mypy 22 个文件、依赖检查通过，11 份语料及 SHA256 校验通过。

原始证据：[checks.json](../eval-results/maintenance-2026-10-16/checks.json)、[测试输出](../eval-results/maintenance-2026-10-16/pytest.txt)、[语料校验](../eval-results/maintenance-2026-10-16/corpus.txt)。测试使用隔离模型替身；本次没有重跑 72×8 完整真实模型检索评测、付费 LLM、Docker、浏览器或云端 CI。

保留原 [freeze.json](../freeze.json)，它只描述 9 月基线，不能拿它校验维护后的代码。当前维护版本使用独立 [freeze-2026-10-16.json](../freeze-2026-10-16.json)，其中明确标注历史评测仅属于基线。验证命令：

```powershell
.venv/Scripts/python.exe scripts/freeze_delivery.py --verify --manifest freeze-2026-10-16.json
```

新清单通过 `--maintenance-of freeze.json --manifest freeze-2026-10-16.json` 创建；脚本拒绝覆盖任何已有清单。原始冻结字节和本次修复历史同时保留，不能因重新计算哈希宣称完整实验已经重跑。

## 2026-09-06 冻结验收

验收日期：2026-09-06。下面区分本地执行、容器执行和未执行事项；配置文件存在不等于云端执行成功。

## 实际结果

| 层级 | 结果 | 原始证据 |
|---|---|---|
| pytest | 54 passed；含分支统计的综合覆盖率约 93.7%，门槛 80% | `validation/4-pytest.txt`、`coverage.json`、`pytest.xml` |
| 静态检查 | Ruff format/check 与 mypy 22 个源文件通过 | `validation/checks.json` 与各检查输出 |
| 真实模型评测 | 72 条 x 8 组全部 completed，0 降级 | `frozen-2026-09-06/summary.json` |
| 真实来源 | 7 个主文件 + 2 个补充页面 hash 一致；两份 PDF 各 10 页可提取 | `source-audit.json` |
| Docker | 构建成功、healthy、非 root；真实重排/向量故障回退/恢复通过 | `docker-validation/results.json` |
| 本地与容器 UI/API | 4 模式、3 视口、日期过滤、引用、422、错误后旧答案清除通过 | `local-smoke/`、`docker-smoke/` |

冻结镜像 ID：`sha256:82900917ec4367779e092e5466354c3ab6697b1c7b21eb042f410e2c6de68c89`，大小 2,484,915,736 bytes（不含模型卷）。程序并非“轻量无依赖”，PyTorch CPU 包和真实模型有明确存储/内存成本。

## 可重复的本地检查

```powershell
.venv/Scripts/python.exe scripts/validate.py
.venv/Scripts/python.exe scripts/audit_sources.py
.venv/Scripts/python.exe -m policy_rag.cli eval eval-results/your-new-run
.venv/Scripts/python.exe scripts/analyze_results.py eval-results/your-new-run
```

`validate.py` 真实调用 Ruff format/check、mypy、pytest 含分支覆盖率和语料 hash 校验，并将退出码、开始/结束时间及原始输出写到 [`eval-results/validation/`](../eval-results/validation/checks.json)。测试覆盖 API 校验、429/503/504、重排/向量故障降级、过滤一致性、索引损坏与失败保留旧版、版本冲突、引用结构、下载白名单以及手算评测公式。测试替身只用于工程单测，不能当真实模型结果。

语料审计 [`source-audit.json`](../eval-results/source-audit.json) 验证 7 个官方 HTML/PDF 文件及 2 个补充页面的真实下载 hash，实际调用 Loader 提取文本。两个 10 页 PDF 已渲染检查首页/末页，末页 v2.3/v2.4 与清单一致；渲染图和全文留在忽略提交的 `data/external/`。没有将 URL 文件名日期认定为生效日。

## Docker 与浏览器

```powershell
.venv/Scripts/python.exe scripts/verify_docker.py
.venv/Scripts/python.exe -m playwright install chromium
.venv/Scripts/python.exe scripts/smoke_demo.py --url http://127.0.0.1:8011 --name docker
```

`verify_docker.py` 实际构建镜像并启动本项目 Compose，等待 `/ready`，调用真实 Reranker；短暂停止**本项目的** Qdrant，验证 `/ready=503` 和检索显式降级 BM25，然后恢复并确认 Hybrid+Rerank 正常。脚本不会停止其他项目容器或删除卷。镜像 ID、字节大小、非 root 用户、Docker health 日志、正常/故障/恢复原始响应保存于 [`docker-validation/results.json`](../eval-results/docker-validation/results.json)，构建日志为同目录 `build.txt`。

浏览器在 1440x1000、390x844、360x800 视口验证真实 API、引用、SVG 图标、候选、无横向溢出、无脚本错误、截图非空，以及失败的新请求不会保留旧答案。四种检索模式、日期排除旧版、明确无证据和输入校验均通过真实 HTTP 检查。证据见 [`docker-smoke/results.json`](../eval-results/docker-smoke/results.json)、[桌面截图](../eval-results/docker-smoke/query-1440.png)、[手机截图](../eval-results/docker-smoke/query-390.png)。本地 Qdrant Local 服务的独立检查见 `eval-results/local-smoke/`。

## 未执行与不等价项

- 真实提供商 LLM 生成评测未执行，没有使用付费 Key。抽取式生成/引用评测已经执行，但不等价于 LLM 生成质量。
- 独立人工 qrels、逐句事实蕴含审核、法律审核未执行。
- GitHub Actions 文件已提供，**未推送触发、未验证云端 CI 成功**。
- 没有正式漏洞扫描认证、生产压力测试、GPU 基准或多租户安全评估。
- `/ready` 成功只代表索引/向量 collection 可访问；真实 Dense/Rerank 已另用请求测试，不能仅靠健康端点宣称模型链路通过。

## 冻结与复查

`freeze.json` 记录交付代码、锁文件、配置、语料和最终报告的 SHA256。Git 对语料/实验文件禁用自动换行转换，避免跨系统 checkout 改变受验证字节。未自动创建 Git 提交，也未修改主项目。运行环境的 cache、模型权重、索引数据库、私有原文和密钥不收入仓库。

校验冻结字节：`.venv/Scripts/python.exe scripts/freeze_delivery.py --verify`。重新运行测试会更新验收时间和输出，故会合理地导致冻结检查提示改变；应在新分支或新发布中记录这些变化，不悄悄覆盖旧报告。
