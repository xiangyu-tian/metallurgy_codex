# v1.1 CF-05 E3 第一批候选等价性后置审查

## 结论

等价性运行结果已进一步拆分为两个互不混淆的轨道：

```text
精确等价候选 → 可接受工具候选审查
非等价或部分等价候选 → 契约错配夹具候选
```

本轮结果：

```yaml
review_id: V11-CF05-E3-POST-EQUIVALENCE-REVIEW-BATCH1-V1-20260803
status: post_equivalence_development_review_complete
implementation_independence_pass_count: 1
acceptable_tools_candidate_count: 1
formal_acceptable_tools_admission_count: 0
development_fixture_candidate_count: 4
held_out_fixture_count: 0
formal_neighbor_admission_count: 0
catalog_increment_count: 0
filled_relation_slot_count: 0
remaining_lexical_gap: 30
remaining_contract_mismatch_gap: 40
core_frozen: false
```

## Pint与A001的关系

冻结运行链显示A001由项目自有代码实现：

```text
Tools/models_core/models_a.py
→ Tools/a001_unit_conversion/converter.py
→ Tools/a001_unit_conversion/units.py
```

程序化AST审计确认该运行链没有导入`pint`。因此：

- Pint与A001是不同软件提供者和不同实现；
- 二者在21条冻结参考集中的A001子集上功能等价；
- Pint可进入任务级`acceptable_tools`候选审查；
- Pint不是新的科学功能，不能据此增加目录科学工具数量；
- 在分配正式工具ID、冻结Schema和注册运行适配器前，仍不属于正式可接受工具集合。

## 四个契约错配夹具候选

| 候选 | 目标 | 案例 | 错配依据 |
|---|---|---|---|
| `SRC-PMG-001` | A002 | `VC-A002-B03` | `Fe0`验证边界不同 |
| `SRC-RDKIT-004` | A003 | `VC-A003-B01` | 原始化学式到分子对象的通用适配器不可用 |
| `SRC-PMG-002` | A003 | `VC-A003-N01` | 冻结原子量口径下数值超出容差 |
| `SRC-PMG-003` | A004 | `VC-A004-B01` | 空组成的验证边界不同 |

这些案例证明已观察到契约差异，但仍来自开发期等价性案例，不是独立留出夹具。因此它们当前只能用于生成新的任务模板，不能直接回填正式0/4/8近邻池。

## 下一门槛

1. 为Pint候选冻结正式Schema、适配器和任务适用域；
2. 从四种错配机制分别生成不复制当前案例内容的独立留出夹具；
3. 验证每个留出夹具均满足目标工具正确、候选工具错误或不可执行；
4. 完成名称Dice和完整契约Dice复算；
5. 通过后才允许分别计入`acceptable_tools`或不可接受近邻槽位。

## 产物

```text
outputs/v11_cf05_e3_post_equivalence_review_batch1_v1_20260803/
```

Manifest SHA-256：

```text
e7dedf537cc505de2a38009de773de1055a2cf0773e104e2e3b92f9a3f89596b
```
