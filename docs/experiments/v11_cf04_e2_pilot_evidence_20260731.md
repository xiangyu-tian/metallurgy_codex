# v1.1 CF-04 E2契约边界变换先导证据

## 结论

CF-04的确定性任务变换和规则复算先导已经完成：

```text
candidate_evidence_status = passed
CF-04 = in_progress
Core Frozen = false
```

本轮证明了五个`verified_core`工具可以自动生成缺参、歧义、契约超域、不支持、不可用、版本错配及多标签组合任务，并由版本化规则重新计算flags和动作。当前还没有温度范围、压力范围和神经网络模型卡契约，因此三类变换明确保留为缺口。

## 1. 数据规模

| 项目 | 数量 |
|---|---:|
| 工具 | 5 |
| ready基线任务 | 5 |
| 变换任务 | 50 |
| 总任务 | 55 |
| 多标签任务 | 15 |
| 变换事件 | 65 |

动作分布：

| 动作 | 数量 |
|---|---:|
| `call` | 5 |
| `clarify` | 24 |
| `refuse` | 26 |

## 2. 已覆盖变换

| 变换 | 事件数 | 派生flag |
|---|---:|---|
| `remove_required_parameter` | 10 | `missing_parameter` |
| `remove_unit` | 2 | `missing_parameter` |
| `make_parameter_ambiguous` | 10 | `ambiguous_parameter` |
| `make_unit_ambiguous` | 2 | `ambiguous_parameter` |
| `contract_out_of_domain` | 15 | `contract_defined_out_of_domain` |
| `unsupported_system` | 5 | `contract_defined_unsupported_system` |
| `unsupported_phase` | 1 | `contract_defined_unsupported_system` |
| `unavailable_tool` | 15 | `unavailable` |
| `version_mismatch` | 5 | `version_mismatch` |

事件数高于单因素任务数，是因为15个多标签任务各包含两个变换事件。

## 3. 动作优先级

规则版本：

```text
e2-readiness-policy-v1.0.0
```

优先级：

```text
missing_parameter / ambiguous_parameter
→ clarify

contract OOD / unsupported system / model-card OOD / version mismatch
→ refuse

unavailable
→ refuse

无flags
→ call
```

多标签任务保留全部底层事实。例如：

```yaml
expected_flags:
  - missing_parameter
  - unavailable
primary_status: missing_or_ambiguous_input
allowed_actions: [clarify]
policy_expected_action: clarify
```

这验证了缺参优先于不可用：系统应先补齐用户输入，而不是用当前不完整请求提前作工具可用性结论。

当前`refuse`表示“不能调用这个目标工具且未提供已验证替代工具”。未来加入替代工具候选后，可以扩展为选择替代工具并计算`Alternative Success Rate`，不能把本轮的单目标工具规则直接外推到多工具替代场景。

## 4. 真值如何产生

本轮没有人工逐题填写flags。生成流程为：

```text
E1b合法基础任务
→ 绑定verified_core工具契约
→ 应用版本化变换
→ 保存changed_fields
→ 按mutation_type映射全部flags
→ 按固定优先级派生primary_status和动作
→ 独立验证器从mutation_events重新计算
```

每条任务保存：

- 来源基础任务和基础任务组；
- 工具、版本、契约ID和契约哈希；
- 结构化参数及请求上下文；
- 一个或多个变换ID；
- 全部底层flags；
- 主要状态、合法动作和政策动作；
- 规则版本。

AI银标和人工主观判断均未进入该真值链。

## 5. 当前无法生成的类别

| 变换 | 状态 | 原因 |
|---|---|---|
| `out_of_temperature_range` | 待补 | 五个契约均未声明温度范围 |
| `out_of_pressure_range` | 待补 | 五个契约均未声明压力范围 |
| `model_card_defined_ood` | 待补 | 当前没有verified神经网络工具和冻结模型卡 |

这些类别没有被伪造为零样本“通过”。后续必须引入具备相应字段和独立验证证据的工具契约。

## 6. 自动审计

审计通过以下检查：

1. 55个任务ID唯一；
2. 65个变换事件ID唯一；
3. 六类核心变换覆盖；
4. 五个verified_core工具均覆盖；
5. 至少15个多标签任务；
6. `call/clarify/refuse`三类动作均覆盖；
7. 所有flags和动作可从规则重新计算；
8. 不使用人工逐题标签；
9. 所有任务保持非确认性候选状态。

测试文件：

```text
Tools/core_freeze/tests/test_v11_cf04_e2_pilot.py
```

## 7. 产物

```text
outputs/v11_cf04_e2_pilot_20260731/
├── e2_pilot_tasks.json
├── mutation_events.json
├── coverage_report.json
├── audit_report.json
└── artifact_manifest.json
```

## 8. 下一步

CF-04尚不能整体通过。下一步应：

1. 对55个结构化任务做语法和可读性抽检；
2. 冻结E2模型策略提示词和输出Schema；
3. 先运行小规模离线/开发先导，检查模型能否输出flags和动作；
4. 再决定E2正式任务规模和重复次数；
5. 后续引入温度、压力及模型卡OOD契约，补齐覆盖缺口。
