# 语料、版本与许可

唯一权威清单是 `data/sources.yaml`：记录 URL、平台、类别、型号、版本、检索适用起止日期、来源类型、实际抓取时间、内容 SHA256、原文 SHA256、补充来源、再分发状态和标注说明。

## 来源范围

当前有 7 份真实来源事实摘要和 4 份合成材料。真实来源包括 Apple Store 退货与退款、Apple 中国硬件保修、华为手机及配件保修、小米手机服务保障、AppleCare+ v2.3/v2.4 官方 PDF。Apple 硬件摘要的浙江差异和有限保修边界另列两个官方补充来源，共 9 个公开 URL。

`data/policies/` 是 AI 辅助写的事实性概述，不是原站全文或授权转载。不能将其中的扩充条件解释成原站原话。文档与条款通过 URL 对应来源；原文仅下载到 `.gitignore` 中的 `data/external/`，不包含在 Docker 构建上下文中。公开可访问不等于拥有再分发许可；本项目未取得品牌方全文转载许可。

`data/fixtures/` 的“星云商城”是虚构平台，文档、API 候选和引用标记 `synthetic=true`。其 v1/v2 对激活、退货期、换货期有明确差异，用于验证过期排除和时间边界，绝不能宣传为任何真实商家的历史规则。默认不指定星云平台的检索会排除全部合成材料。

## 日期语义

真实页面没有可靠声明统一的政策生效起止时间，因此 `effective_from=null`、`effective_to=null`、`validity_basis=unknown`。抓取时间仅表示观察快照的时间；`snapshot-2026-09-06` 不是官方版本号。PDF 的 v2.3/v2.4 是文档版本，但 URL 中的日期不能证明它们对每一份合同的适用期，也不能推定新文档自动替代旧合同。

一旦查询指定 `as_of_date`，未知适用期文档会被排除，返回无证据时拒答。确定的历史日期实验仅对合成规则有效。未来真实业务需要专人维护经确认的条款适用区间、地区和渠道，不应修改代码以猜测日期。

## 可复现下载与导入

```powershell
.venv/Scripts/python.exe -m policy_rag.cli fetch-sources
.venv/Scripts/python.exe -m policy_rag.cli inspect-document data/external/applecare-plus-cn-v2.4.pdf
.venv/Scripts/python.exe -m policy_rag.cli import-snapshot applecare-plus-cn-v2.4 data/external/private-manifest.yaml
```

下载仅允许清单中的官方 HTTPS 主机，检查每次跳转、不携带账号 Cookie、有限重试、有单文件大小上限。导入脚本生成独立私有清单，再用 `POLICY_RAG_SOURCE_MANIFEST` 和独立 `POLICY_RAG_INDEX_ROOT` 建立私有索引；不自动改动冻结评测语料。

网页随时间变化时原文 hash 变化是正常现象，脚本不声称未来能重新下载完全一致的字节。默认版本的可复现性依靠仓库中摘要、清单、固定模型与锁文件；私有原文实验必须另存实验快照，不混入默认摘要实验。

## 标注来源

72 条固定查询：精确术语 12、口语 12、多条件 12、跨文档 8、版本 10、无答案 12、困难负例 6。每条都有相关文档 ID、来源 URL 或合成 URN、标注来源和边界备注。全部由 AI 辅助构造，未由独立人工评审；不是线上用户日志、不是大规模真实电商语料、不是独立测试金标。没有使用标签驱动在线检索或回答。
