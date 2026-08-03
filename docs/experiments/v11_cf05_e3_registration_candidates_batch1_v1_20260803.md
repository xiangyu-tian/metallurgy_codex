# v1.1 CF-05 E3 第一批非正式注册候选包

## 结论

第一批5个来源候选已经从临时来源ID推进到稳定的非正式候选命名空间：

```yaml
package_id: V11-CF05-E3-REGISTRATION-CANDIDATES-BATCH1-V1-20260803
candidate_id_namespace: E3C
candidate_registration_count: 5
candidate_id_collision_count: 0
runtime_smoke_case_count: 10
runtime_smoke_pass_count: 10
acceptable_equivalent_candidate_count: 1
lexical_neighbor_candidate_count: 1
contract_mismatch_candidate_count: 3
evidence_insufficient_count: 0
formal_catalog_size_before: 120
formal_catalog_size_after: 120
formal_catalog_increment_count: 0
formal_neighbor_admission_count: 0
external_api_calls: 0
core_frozen: false
```

## 稳定候选ID

| 候选ID | 来源候选 | 目标 | 包装能力 | 当前关系候选 |
|---|---|---|---|---|
| `E3C001` | `SRC-PINT-001` | A001 | Pint标量单位换算 | 可接受等价 |
| `E3C002` | `SRC-PMG-001` | A002 | pymatgen化学式解析 | 契约错配 |
| `E3C003` | `SRC-RDKIT-004` | A003 | RDKit平均分子量 | 词法近邻 |
| `E3C004` | `SRC-PMG-002` | A003 | pymatgen组成式量 | 契约错配 |
| `E3C005` | `SRC-PMG-003` | A004 | pymatgen分数组成归一化 | 契约错配 |

`E3C`是候选命名空间，不是正式A—G工具编号。程序已验证这5个ID与当前120条目录ID没有碰撞。

## 可调用包装器

统一包装器位于：

```text
Tools/core_freeze/e3_routing/candidate_runtime_adapters.py
```

每个候选均具有：

- 唯一稳定候选ID；
- 固定包及版本；
- 完整OpenAI函数Schema；
- 严格顶层参数字段；
- 正常案例；
- 失败案例；
- 统一`success/result/error_code/error`返回契约。

10个冒烟案例全部满足预期成功或失败结果。该测试只验证包装器可调用性和返回契约，不把候选升级为科学真值来源。

## 关系判定

关系候选由三类证据联合产生：

1. 名称及完整契约文本二元Dice；
2. `supported_systems`、`data_or_model_version`、`service_status`结构化差异；
3. 上一阶段不重复输入的实际执行夹具。

Pint虽然在结构字段上与A001存在版本和服务状态差异，但7条等价证据优先，因此不能错误标记为不可接受近邻。RDKit候选满足词法阈值但输入是SMILES，因此进入词法近邻候选。其余3个候选同时具备功能重叠、结构化契约差异和执行错配证据。

## 尚未正式准入的原因

当前生命周期统一为：

```text
candidate_registered_nonformal
```

并固定：

```yaml
formal_catalog_entry: false
formal_execution_allowed: false
formal_pool_inclusion_allowed: false
```

下一步需要形成独立的准入决策包，明确：

- 哪些候选只进入任务级`acceptable_tools`；
- 哪些候选进入词法或契约错配池；
- 候选是否计入工具数量；
- 池内任务与当前开发夹具如何隔离；
- 准入后如何重新计算30/40缺口。

## 产物

```text
outputs/v11_cf05_e3_registration_candidates_batch1_v1_20260803/
```

Manifest SHA-256：

```text
d2218c285010b2e74751061293c84ea67253a5f7076cdb2d306bc34465c623f7
```
