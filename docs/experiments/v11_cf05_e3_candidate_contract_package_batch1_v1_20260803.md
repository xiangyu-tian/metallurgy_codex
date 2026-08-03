# v1.1 CF-05 E3第一批候选契约与等价性测试包

## 1. 结论

第一批候选已经从“来源能力名称”推进到结构化契约与测试设计：

```yaml
package_id: V11-CF05-E3-CANDIDATE-CONTRACT-PACKAGE-BATCH1-V1-20260803
status: contract_and_equivalence_design_complete_execution_pending
contract_draft_count: 12
structurally_complete_contract_count: 12
equivalence_test_plan_count: 5
equivalence_reference_case_count: 21
dependency_import_available_count: 0
version_locked_contract_count: 0
implemented_contract_count: 0
execution_verified_contract_count: 0
independence_verified_contract_count: 0
admission_ready_contract_count: 0
catalog_increment_count: 0
filled_relation_slot_count: 0
external_api_calls: 0
core_frozen: false
```

“结构完整”只表示每份草案已经包含输入、输出、单位、适用域、排除条件、错误码、来源操作和限制。它不表示软件已经安装、包装器已经实现或候选已经成为独立工具。

## 2. 12项契约草案

| 目标 | 数量 | 契约方向 |
|---|---:|---|
| A001 | 1 | Pint显式Context转换 |
| A002 | 3 | SMILES解析、SMARTS解析、Canonical SMILES |
| A003 | 2 | ExactMolWt、HeavyAtomMolWt |
| A004 | 4 | 最简组成、原子分数、质量分数、质量到摩尔组成 |
| B019 | 2 | 相稳定性筛查、二元相图映射 |

草案使用临时候选ID，不分配正式`A999/B999`式工具ID。所有条目统一保持：

```yaml
draft_status: structurally_complete_execution_unverified
version_lock_status: pending_dependency_installation_and_lock
implementation_status: not_implemented
dependency_import_available: false
execution_allowed: false
admission_allowed: false
```

## 3. 词法结果

使用冻结字符二元Dice，对目标语义别名以及双方结构化输入/输出字段进行复算：

```yaml
name_threshold_pass_count: 9
structured_contract_threshold_pass_count: 12
final_lexical_relation_pass_count: 0
final_contract_mismatch_relation_pass_count: 0
```

结构化契约文本达到阈值只说明字段层面有相似性。候选尚未执行，也没有独立性证据和“目标有效、候选无效”夹具，因而不能把12项计入词法或契约近邻。

## 4. 五项等价性测试

测试计划直接绑定`verified_core`中21个独立参考案例：

- Pint普通单位换算相对A001；
- pymatgen Composition解析相对A002；
- RDKit MolWt相对A003；
- pymatgen Composition weight相对A003；
- pymatgen fractional composition相对A004。

判定不仅比较数值，还要求：

- 成功与失败边界一致；
- 输入适配器能够覆盖目标完整适用域；
- 原子量、单位和软件版本约定一致；
- 不能依赖逐题人工补充的化学知识映射。

因此，RDKit MolWt即使在几个分子上与A003数值接近，只要“化学式到SMILES”不能在目标语法范围内确定性转换，就不能称为操作层面的完全等价工具。

## 5. 环境事实

冻结`.venv`中当前未发现：

```yaml
pint: false
rdkit: false
pymatgen: false
pycalphad: false
```

本轮没有安装依赖，也没有生成候选运行结果。后续若要执行，应在单独的隔离环境中锁定Python、四个包及热力学数据库版本，避免改变现有平台运行环境。

## 6. 下一门槛

1. 审批是否创建隔离候选验证环境；
2. 锁定各依赖版本和来源哈希；
3. 先执行5项等价性测试；
4. 只为被判为不等价或部分等价的候选实现最小包装器；
5. 对12项契约执行正常、边界和失败案例；
6. 再进行独立性审查和契约错配夹具构造。

这种顺序可以避免为最终会被判为等价工具的候选重复开发包装器。

## 7. 产物

```text
outputs/v11_cf05_e3_candidate_contract_package_batch1_v1_20260803/
```

Manifest SHA-256：

```text
2d484aef04e5bbcb7488e9aed93fab59d66b6ff057af80ac5a92f18446ab9732
```
