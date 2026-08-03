# v1.1 CF-05 E3官方来源候选第一批

## 1. 结论

本批次完成的是“能力存在性”的官方来源绑定，不是新工具准入：

```yaml
batch_id: V11-CF05-E3-SOURCE-CANDIDATES-BATCH1-20260803
status: source_binding_passed_admission_review_pending
official_source_count: 10
source_bound_candidate_count: 20
accepted_candidate_count: 0
catalog_increment_count: 0
filled_relation_slot_count: 0
remaining_lexical_gap: 30
remaining_contract_mismatch_gap: 40
external_api_calls: 0
formal_pool_generation_allowed: false
core_frozen: false
```

所有候选统一标记为：

```yaml
candidate_status: source_bound_candidate_unreviewed
relation_claim_status: proposed_pending_fixture
independence_status: pending
count_toward_catalog: false
execution_allowed: false
```

因此，本批次不能用于声称目录已经超过120条，也不能进入0/4/8正式工具池。

## 2. 官方来源与能力范围

第一批只使用软件项目的官方文档：

- Pint Contexts：上下文相关的单位换算和显式跨量纲转换；
- RDKit `rdmolfiles`、`Chem`、`Descriptors`：SMILES/SMARTS解析、规范化表示和分子量描述符；
- pymatgen `Composition`：化学式解析、分数组成、最简组成、原子/质量分数和质量基准转换；
- pycalphad equilibrium、results、stability、mapping、plot：平衡计算、相分数读取、稳定性筛查、二元映射和三元图。

来源页面及其定位符已写入`source_manifest.json`。来源能够证明相关API或工作流存在，但不能独立证明它们满足本项目对“独立工具”和“目标近邻”的定义。

## 3. 候选覆盖

| 目标工具 | 来源绑定候选数 | 主要候选族 |
|---|---:|---|
| A001 | 2 | Pint Context |
| A002 | 4 | RDKit解析、pymatgen Composition |
| A003 | 4 | RDKit分子量描述符、pymatgen Composition weight |
| A004 | 5 | pymatgen Composition变换/分数读取 |
| B019 | 5 | pycalphad平衡、结果、映射与绘图 |

这些数字只是待审查能力条目数，不能相加为20个独立工具。尤其是：

- 同一软件库的多个函数可能只是一套引擎的不同操作；
- 某些函数可能与A001—A004或B019科学等价，应被判为可接受等价工具而非干扰近邻；
- 绘图和结果读取可能只是后处理操作，不能作为独立计算工具；
- 精确分子量、重原子分子量等虽与摩尔质量名称相近，但输出量不同，必须由可复算任务夹具证明契约错配关系。

## 4. 下一准入门

每个候选必须依次通过：

1. 语义重复审查：与现有120条目录逐项比较，不只检查字符串相等；
2. 工具独立性审查：确认是否具有独立入口、输入输出契约、错误边界和版本身份；
3. 可接受等价性审查：若能正确完成目标任务，则不得作为不可接受近邻；
4. 词法关系复算：使用冻结Dice规则计算名称和契约文本相似度；
5. 契约错配夹具：形成“目标有效、候选因明确边界无效”的可复算样例；
6. 条目准入：通过完整Schema、来源、限制和证据检查后才分配正式工具ID；
7. 槽位回填：只有准入条目才能减少30/40关系缺口，并重新构造嵌套池。

若候选在任一步被判定为同一引擎操作、科学等价或关系不足，应保留拒绝记录，不得为了凑足8个近邻而降级标准。

## 5. 产物

```text
outputs/v11_cf05_e3_source_candidates_batch1_20260803/
```

包含候选注册表、官方来源清单、预检报告、输入快照和哈希Manifest。

Manifest SHA-256：

```text
049df151129f8512df9a2b89ce9d8dc42d83eb41178c8ce96543836cc328326b
```
