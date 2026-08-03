# v1.1 CF-05 E3第一批候选准入前筛查

## 1. 结论

第一批20项官方来源候选完成了离线准入前筛查：

```yaml
screening_id: V11-CF05-E3-CANDIDATE-SCREENING-BATCH1-V1-20260803
status: pre_admission_screen_complete_followup_evidence_required
candidate_count: 20
contract_draft_queue: 12
equivalence_test_required: 5
screened_out_before_fixture: 3
preliminary_alias_name_pass_count: 9
accepted_candidate_count: 0
catalog_increment_count: 0
filled_relation_slot_count: 0
remaining_lexical_gap: 30
remaining_contract_mismatch_gap: 40
external_api_calls: 0
core_frozen: false
```

本筛查不是专家金标准，也不是正式工具准入决定。它只依据已冻结目标契约、120条目录、官方来源所描述的操作和冻结的字符二元Dice阈值，把后续证据工作分流。

## 2. 三条筛查队列

### 2.1 完整契约起草队列：12项

| 目标 | 数量 | 候选方向 |
|---|---:|---|
| A001 | 1 | 显式Context跨量纲转换 |
| A002 | 3 | SMILES、SMARTS、Canonical SMILES |
| A003 | 2 | ExactMolWt、HeavyAtomMolWt |
| A004 | 4 | 最简组成、原子分数、质量分数、质量到摩尔组成 |
| B019 | 2 | 相稳定性筛查、二元相图映射 |

这些候选具有与目标不同的输入、输出或适用域假设，可以继续起草JSON可调用契约。但“可起草”不代表已证明为独立工具，也不代表已经构成契约错配近邻。

### 2.2 等价性测试队列：5项

- Pint普通Context单位换算相对A001；
- pymatgen Composition解析相对A002；
- RDKit平均分子量与pymatgen Composition weight相对A003；
- pymatgen fractional composition相对A004。

这些能力可能正确完成目标任务。若测试证明等价，它们只能进入目标的可接受工具集合，不能作为“不应选择”的干扰近邻。

### 2.3 夹具前筛出：3项

- `SRC-PYCAL-001`：现有目录已有`B023 run_calphad_equilibrium`，语义目标重复；
- `SRC-PYCAL-002`：只读取既有平衡计算结果中的相分数，依赖上游计算；
- `SRC-PYCAL-005`：只绘制已有平衡数据，不是独立计算工具。

筛出表示不再投入近邻夹具构造，不等于否认相应软件API本身有用。

## 3. 初步词法结果的限制

完整契约起草队列中有9项的英文能力别名相对目标语义别名达到冻结的名称Dice阈值：

```yaml
A002: 3
A003: 2
A004: 4
```

A001和B019当前没有候选通过“别名名称”阈值。由于候选尚未形成完整`tool_name + core_method + main_input + main_output`文本，契约文本Dice仍为`null`。因此这9项只能进入下一轮词法复核，不能减少30个词法缺口。

## 4. 下一门槛

下一阶段按两条相互隔离的路径推进：

1. 为12项契约队列起草完整输入、输出、单位、适用系统、版本、可用性和限制；
2. 为5项等价性队列建立与目标相同任务的对照测试，先判断是否属于可接受工具；
3. 对契约队列复算完整词法与功能Dice；
4. 只有通过独立性审查且不等价的条目，才构造“目标有效、候选无效”的契约错配夹具；
5. 夹具和来源均通过后才能分配正式工具ID并回填关系槽位。

这种顺序避免把正确的替代工具错误标成干扰项，也避免把一个计算引擎的读取、绘图操作重复计数。

## 5. 产物

```text
outputs/v11_cf05_e3_candidate_screening_batch1_v1_20260803/
```

Manifest SHA-256：

```text
57d0ac3daff33da2e4c3287568cce74403594645b6ec57c8ea84a27ef782619a
```
