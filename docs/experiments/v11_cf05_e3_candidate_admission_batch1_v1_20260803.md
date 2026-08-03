# v1.1 CF-05 E3 第一批候选准入决策

## 结论

第一批5个非正式注册候选已通过独立的证据准入决策：

```yaml
decision_id: V11-CF05-E3-CANDIDATE-ADMISSION-BATCH1-V1-20260803
status: evidence_registry_admission_complete_formal_pool_pending
acceptable_tools_registry_admission_count: 1
neighbor_relation_registry_admission_count: 4
lexical_relation_admission_count: 1
contract_mismatch_relation_admission_count: 3
scientific_function_catalog_increment_count: 0
formal_catalog_size: 120
formal_pool_inclusion_count: 0
lexical_gap_before: 30
lexical_gap_after: 29
contract_mismatch_gap_before: 40
contract_mismatch_gap_after: 37
external_api_calls: 0
core_frozen: false
```

## 三类计数被明确分离

本次准入没有把以下概念混为一谈：

| 概念 | 本轮结果 | 含义 |
|---|---:|---|
| 任务级可接受工具关系 | 1 | A001任务可把`E3C001`视为等价候选 |
| 近邻关系证据槽位 | 4 | 1个词法、3个契约错配关系已有完整证据 |
| 新科学功能目录条目 | 0 | 等价实现和相似实现不重复增加科学功能数 |
| 正式确认性池条目 | 0 | 尚未生成任务隔离后的0/4/8池 |

因此，正式目录仍为120，但CF-05的关系证据缺口可以按已经满足的槽位重新计算。

## 可接受工具准入

`E3C001`进入A001任务级可接受工具关系：

```json
{
  "target_tool_id": "A001",
  "acceptable_tool_ids": ["A001", "E3C001"]
}
```

准入同时要求：

- 首轮冻结案例精确等价；
- 实现提供者与A001独立；
- 科学功能不被误称为新增功能；
- 7条不重复输入继续等价；
- 包装器正常/失败契约通过；
- 相似度中的结构差异不能覆盖实际等价证据。

## 近邻关系准入

| 候选 | 目标 | 准入关系 | 证据 |
|---|---|---|---|
| `E3C002` | A002 | 契约错配 | 零计量验证边界不同 |
| `E3C003` | A003 | 词法近邻 | 名称/契约文本相似，但输入要求SMILES |
| `E3C004` | A003 | 契约错配 | 原子量数据版本导致结果超容差 |
| `E3C005` | A004 | 契约错配 | 全零组成验证边界不同 |

每个候选只占一个目标下的一种关系槽位。即便算法同时发现多种相似性，也不会重复计算容量。

## 缺口复算

缺口不是手工从30/40直接扣除，而是逐目标读取原始扩展需求矩阵后复算：

```text
A002: contract_mismatch 0 → 1
A003: lexical 4 → 5
A003: contract_mismatch 0 → 1
A004: contract_mismatch 0 → 1
```

因此：

```text
lexical_gap: 30 → 29
contract_mismatch_gap: 40 → 37
```

## 为什么仍未生成正式工具池

当前完成的是关系证据注册，不是确认性池发布。下一阶段还需要：

1. 把已准入关系与目录Schema合并为池构造输入；
2. 为每个目标继续补足剩余近邻；
3. 保证0/4/8池嵌套且关系类型互斥；
4. 把开发夹具与正式路由任务内容隔离；
5. 完成池manifest和泄漏审计后才允许正式执行。

## 产物

```text
outputs/v11_cf05_e3_candidate_admission_batch1_v1_20260803/
```

Manifest SHA-256：

```text
8c66557f7cdfe03c36e2d412534f5bc213109ce0ad4313e421f3d7ffbb88f1f9
```
