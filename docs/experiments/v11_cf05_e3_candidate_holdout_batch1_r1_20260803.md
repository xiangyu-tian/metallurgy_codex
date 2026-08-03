# v1.1 CF-05 E3 候选适配器与错配关系留出验证

## 结论

第一批候选已经完成第二层本地验证。该层使用与27条冻结参考案例不完全重复的新输入，分别验证：

1. Pint适配器在A001冻结适用域内是否继续等价；
2. 四种契约错配机制能否在新输入上复现。

```yaml
run_id: V11-CF05-E3-CANDIDATE-HOLDOUT-BATCH1-R1-20260803
status: completed_nonconfirmatory_holdout_evidence
input_novelty_passed: true
acceptable_equivalence_case_count: 7
acceptable_equivalence_pass_count: 7
pint_runtime_verification_passed: true
pint_registration_candidate_ready: true
contract_mismatch_case_count: 4
contract_mismatch_fixture_pass_count: 4
relation_fixture_verification_passed: true
formal_acceptable_tools_admission_count: 0
formal_neighbor_admission_count: 0
catalog_increment_count: 0
filled_relation_slot_count: 0
external_api_calls: 0
core_frozen: false
```

## Pint适配器

新增开发版契约和运行适配器：

```text
Tools/core_freeze/e3_routing/pint_acceptable_candidate_contract_v1.json
Tools/core_freeze/e3_routing/pint_unit_adapter.py
```

适配器只接受A001契约已经冻结的8个有向单位对，不把Pint的全部能力无条件暴露给实验。7个新数值案例全部在`1e-4`绝对容差内与A001一致，包括两个仿射温标案例。

因此Pint候选当前达到：

```text
development contract frozen
runtime verified
registration candidate ready
```

但尚未达到：

```text
formal tool ID assigned
formal acceptable_tools admitted
formal E3 pool included
```

## 新错配输入

| 候选 | 新输入 | 复现的差异 |
|---|---|---|
| `SRC-PMG-001` | `O0` | A002拒绝零计量，pymatgen接受为空组成 |
| `SRC-RDKIT-004` | `Mg(OH)2` | A003可按原始化学式计算，RDKit需要分子对象且不存在通用确定性适配器 |
| `SRC-PMG-002` | `Al2O3` | 两者均执行，但冻结原子量口径的结果差异超过容差 |
| `SRC-PMG-003` | `Fe=0,C=0,Si=0` | A004拒绝全零组成，pymatgen接受为空分数组成 |

去重按`target_tool_id + canonical JSON input`执行：11条新输入与27条参考案例均无完全重复，内部也没有重复。

## 研究解释边界

这些输入在观察第一轮错误机制后构造，因此属于“后置机制留出”，不是确认性测试集。它们足以验证适配器与关系夹具的工程可执行性，但不能单独支持论文效果结论。

正式近邻准入还需要：

- 给候选分配稳定工具ID和完整Schema；
- 实现真实可调用包装器；
- 复算名称及完整契约相似度；
- 将关系证据写入目录注册记录；
- 另行生成与路由评测任务隔离的正式任务实例。

## 产物

```text
outputs/v11_cf05_e3_candidate_holdout_batch1_r1_20260803/
```

Manifest SHA-256：

```text
0e66f61010d7e3eb06a43a19c02e4a4f4e76d0662628bc7d0fc9bc2237dbcc3b
```
