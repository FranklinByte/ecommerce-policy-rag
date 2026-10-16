# Fixed Regression Experiment

AI-assisted fixed regression; NOT independently human-reviewed; NOT model generalization evidence

Retrieval is document-level: deduplicate document IDs from top-5 returned chunks. MRR is truncated at 5. No-answer cases are excluded from retrieval denominators.

| Experiment | R@1 | R@3 | R@5 | MRR@5 | nDCG@5 | p50 ms | p95 ms | Refusal accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| structure-bm25 | 0.8833 | 1.0000 | 1.0000 | 0.9722 | 0.9791 | 0.4416 | 0.9138 | 0.9167 |
| structure-dense | 0.8667 | 0.9917 | 0.9917 | 0.9667 | 0.9700 | 49.7732 | 62.6529 | 1.0000 |
| structure-hybrid | 0.8833 | 1.0000 | 1.0000 | 0.9750 | 0.9813 | 52.7675 | 70.5004 | 1.0000 |
| structure-hybrid_rerank | 0.8917 | 1.0000 | 1.0000 | 0.9750 | 0.9810 | 3443.2526 | 3844.1962 | 1.0000 |
| sliding-bm25 | 0.8917 | 1.0000 | 1.0000 | 0.9833 | 0.9864 | 1.4461 | 4.1906 | 0.9167 |
| sliding-dense | 0.9000 | 1.0000 | 1.0000 | 0.9833 | 0.9874 | 51.5878 | 68.7007 | 1.0000 |
| sliding-hybrid | 0.9083 | 1.0000 | 1.0000 | 0.9917 | 0.9925 | 51.9449 | 70.4471 | 1.0000 |
| sliding-hybrid_rerank | 0.9000 | 1.0000 | 1.0000 | 0.9833 | 0.9847 | 4035.4817 | 10647.6757 | 1.0000 |

## Generation and Failure Analysis

Citation precision is relevance of cited document IDs, not entailment or legal correctness. Empty citations have undefined precision; recall is zero for answerable refusals. See summary.json for coverage and acceptance rate, and each experiment's failures.json for categorized cases.

Paid LLM generation and independent human correctness review are not implied by extractive-v1 results. Warmup time is recorded separately; per-query latency includes computation, not model download. Single sequential run, not a load benchmark.
