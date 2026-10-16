# Categorized Failures and Resources

AI-assisted fixed labels, not independent human judgement. An answerable refusal counts as a generation failure; document recall does not verify the particular cited sentence.

## structure-bm25

Retrieval R@5 failures: 0. Generation/citation failures: 29/72.

| Category | Generation/citation failures |
|---|---:|
| colloquial | 10 |
| cross_document | 3 |
| exact | 2 |
| hard_negative | 5 |
| multi_condition | 1 |
| no_answer | 1 |
| version_conflict | 7 |

Representative cases (first five by fixed dataset order):

- Q010 / exact: HOME-REF-520 的主要部件保修多久？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q012 / exact: v2.3 AppleCare+ 电池容量低于多少可以申请服务？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q013 / colloquial: 官网买的苹果手机到了十天了，觉得手感不行，能退吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q014 / colloquial: 苹果给我退的钱怎么还没到微信钱包？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q015 / colloquial: 平板的屏幕过了一年才坏，是不是肯定自费？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。

Index: 43 chunks, 28.622 s, 402670 local bytes; process peak/current RSS at build 706.5 MiB; RSS after queries 169.3 MiB.

## structure-dense

Retrieval R@5 failures: 1. Generation/citation failures: 11/72.

| Category | Generation/citation failures |
|---|---:|
| colloquial | 3 |
| cross_document | 1 |
| exact | 3 |
| hard_negative | 1 |
| multi_condition | 2 |
| version_conflict | 1 |

Representative cases (first five by fixed dataset order):

- Q009 / exact: NEBULA-P2 质量问题换货有多少天？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q010 / exact: HOME-REF-520 的主要部件保修多久？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q011 / exact: INK-XL-62 墨盒开封后能无理由退货吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q015 / colloquial: 平板的屏幕过了一年才坏，是不是肯定自费？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q019 / colloquial: 华为手写笔的那个尖磨坏了，能免费给换吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。

Index: 43 chunks, 28.622 s, 402670 local bytes; process peak/current RSS at build 706.5 MiB; RSS after queries 531.2 MiB.

## structure-hybrid

Retrieval R@5 failures: 0. Generation/citation failures: 13/72.

| Category | Generation/citation failures |
|---|---:|
| colloquial | 6 |
| cross_document | 1 |
| exact | 3 |
| hard_negative | 1 |
| multi_condition | 1 |
| version_conflict | 1 |

Representative cases (first five by fixed dataset order):

- Q009 / exact: NEBULA-P2 质量问题换货有多少天？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q010 / exact: HOME-REF-520 的主要部件保修多久？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q011 / exact: INK-XL-62 墨盒开封后能无理由退货吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q013 / colloquial: 官网买的苹果手机到了十天了，觉得手感不行，能退吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q015 / colloquial: 平板的屏幕过了一年才坏，是不是肯定自费？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。

Index: 43 chunks, 28.622 s, 402670 local bytes; process peak/current RSS at build 706.5 MiB; RSS after queries 533.9 MiB.

## structure-hybrid_rerank

Retrieval R@5 failures: 0. Generation/citation failures: 19/72.

| Category | Generation/citation failures |
|---|---:|
| colloquial | 9 |
| cross_document | 5 |
| exact | 1 |
| hard_negative | 2 |
| multi_condition | 2 |

Representative cases (first five by fixed dataset order):

- Q011 / exact: INK-XL-62 墨盒开封后能无理由退货吗？ Refused=True; cited=[]; reason=检索到同一政策系列的多个版本，请明确版本或提供可核实的适用日期。
- Q013 / colloquial: 官网买的苹果手机到了十天了，觉得手感不行，能退吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q014 / colloquial: 苹果给我退的钱怎么还没到微信钱包？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q015 / colloquial: 平板的屏幕过了一年才坏，是不是肯定自费？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q017 / colloquial: 我把华为手机发票弄丢了，这下没法保修了吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。

Index: 43 chunks, 28.622 s, 402670 local bytes; process peak/current RSS at build 706.5 MiB; RSS after queries 1224.2 MiB.

## sliding-bm25

Retrieval R@5 failures: 0. Generation/citation failures: 38/72.

| Category | Generation/citation failures |
|---|---:|
| colloquial | 12 |
| cross_document | 4 |
| exact | 5 |
| hard_negative | 5 |
| multi_condition | 1 |
| no_answer | 1 |
| version_conflict | 10 |

Representative cases (first five by fixed dataset order):

- Q002 / exact: AM115 有线耳机保修期限是多久？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q009 / exact: NEBULA-P2 质量问题换货有多少天？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q010 / exact: HOME-REF-520 的主要部件保修多久？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q011 / exact: INK-XL-62 墨盒开封后能无理由退货吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q012 / exact: v2.3 AppleCare+ 电池容量低于多少可以申请服务？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。

Index: 16 chunks, 3.986 s, 220424 local bytes; process peak/current RSS at build 750.2 MiB; RSS after queries 1226.6 MiB.

## sliding-dense

Retrieval R@5 failures: 0. Generation/citation failures: 26/72.

| Category | Generation/citation failures |
|---|---:|
| colloquial | 8 |
| cross_document | 2 |
| exact | 5 |
| hard_negative | 2 |
| multi_condition | 6 |
| version_conflict | 3 |

Representative cases (first five by fixed dataset order):

- Q001 / exact: Apple Store 的退货窗口是多少个自然日？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q004 / exact: PC 电源适配器及数据线保修是 24 个月吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q009 / exact: NEBULA-P2 质量问题换货有多少天？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q010 / exact: HOME-REF-520 的主要部件保修多久？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q011 / exact: INK-XL-62 墨盒开封后能无理由退货吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。

Index: 16 chunks, 3.986 s, 220424 local bytes; process peak/current RSS at build 750.2 MiB; RSS after queries 1226.9 MiB.

## sliding-hybrid

Retrieval R@5 failures: 0. Generation/citation failures: 27/72.

| Category | Generation/citation failures |
|---|---:|
| colloquial | 9 |
| cross_document | 2 |
| exact | 5 |
| hard_negative | 2 |
| multi_condition | 6 |
| version_conflict | 3 |

Representative cases (first five by fixed dataset order):

- Q001 / exact: Apple Store 的退货窗口是多少个自然日？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q004 / exact: PC 电源适配器及数据线保修是 24 个月吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q009 / exact: NEBULA-P2 质量问题换货有多少天？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q010 / exact: HOME-REF-520 的主要部件保修多久？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q011 / exact: INK-XL-62 墨盒开封后能无理由退货吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。

Index: 16 chunks, 3.986 s, 220424 local bytes; process peak/current RSS at build 750.2 MiB; RSS after queries 1227.1 MiB.

## sliding-hybrid_rerank

Retrieval R@5 failures: 0. Generation/citation failures: 15/72.

| Category | Generation/citation failures |
|---|---:|
| colloquial | 8 |
| cross_document | 4 |
| exact | 1 |
| hard_negative | 1 |
| multi_condition | 1 |

Representative cases (first five by fixed dataset order):

- Q011 / exact: INK-XL-62 墨盒开封后能无理由退货吗？ Refused=True; cited=[]; reason=检索到同一政策系列的多个版本，请明确版本或提供可核实的适用日期。
- Q013 / colloquial: 官网买的苹果手机到了十天了，觉得手感不行，能退吗？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q014 / colloquial: 苹果给我退的钱怎么还没到微信钱包？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q015 / colloquial: 平板的屏幕过了一年才坏，是不是肯定自费？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。
- Q016 / colloquial: 华为手机才拿到手五天，就自己黑屏了，售后能做啥？ Refused=True; cited=[]; reason=最高相关证据低于配置阈值，需补充信息或人工确认。

Index: 16 chunks, 3.986 s, 220424 local bytes; process peak/current RSS at build 750.2 MiB; RSS after queries 1329.0 MiB.

## Interpretation Limits

Thresholds are uncalibrated engineering defaults. Model scores and RRF are not probabilities. Latency is one sequential CPU regression run, not concurrent-load performance. Index timings include cold model load only on the first build in a process. Windows peak_wset is a process-lifetime high-water mark, not memory allocated solely by indexing; on Linux the fallback is current RSS. Qdrant Server disk use is not included in local directory size.
