# v1.1 CF-04 E2双层边界门控候选

## 结论

E2双层边界门控v1候选已经完成本地实现、数据修复和离线功能验证：

```text
candidate_status = local_candidate_prepared_not_authorized
external_api_calls = 0
CF-04 = in_progress
Core Frozen = false
```

候选将边界判断拆成两个职责：

```text
确定性结构检查
→ missing_parameter
→ ambiguous_parameter
→ unavailable
→ version_mismatch

LLM契约语义检查
→ contract_defined_out_of_domain
→ contract_defined_unsupported_system
→ model_card_defined_ood

有序合并全部flags
→ 冻结政策派生primary_status和action
```

离线结果证明代码链可以正确执行，但尚未测量LLM在修复后任务上的语义分类性能。

## 1. 为什么先修数据而不是直接实现门控

对原55条任务进行可观察性审计时发现4条缺陷：

| 任务 | 组合变换 | 缺陷 |
|---|---|---|
| `E2P-A001-11` | ambiguous + OOD | OOD补丁覆盖歧义单位 |
| `E2P-A002-09` | ambiguous + OOD | OOD补丁覆盖歧义化学式 |
| `E2P-A003-09` | ambiguous + OOD | OOD补丁覆盖歧义化学式 |
| `E2P-B019-12` | ambiguous + OOD | OOD补丁覆盖歧义成分 |

原生成流程为：

```text
应用make_parameter_ambiguous
→ 在字段中写入显式歧义标记
→ 应用contract_out_of_domain
→ 同一标量字段被OOD值覆盖
→ expected_flags仍从变换历史得到两个flags
→ 模型最终只看到OOD状态
```

A004的相同组合因为目标字段是字典，`deep_update`偶然保留了歧义标记，导致同类变换产生不一致行为。

该缺陷意味着：

> 金标签记录了变换历史，但模型回答只能依据最终输入；历史上曾经存在、最终已经消失的事实不能成为金标准。

## 2. 对v1.1结果的影响

v1.1原始结果保持不可变：

```text
flags完全匹配 = 48/55
action正确 = 49/55
```

其中4条错误来自不可观察标签。仅用于开发诊断，排除这4条后：

```text
可评分任务 = 51
flags完全匹配 = 48/51 = 94.12%
action正确 = 49/51 = 96.08%
```

这不是新的正式得分，也不能用于确认性结论。它只说明不能继续把四条任务归因于模型。

原始数据集、API响应和分析均未删除或覆盖。修复采用新的数据集版本。

## 3. E2任务v2候选

新数据集：

```text
E2-CONTRACT-BOUNDARY-PILOT-V2-CANDIDATE-20260731
```

保持：

| 项目 | 数量 |
|---|---:|
| 工具 | 5 |
| 任务 | 55 |
| 变换事件 | 65 |
| 联合ambiguous + OOD任务 | 5 |
| call | 5 |
| clarify | 24 |
| refuse | 26 |

但任务ID改为：

```text
E2V2-...
```

避免与原`E2P-...`任务混淆。

### 联合可观察状态

v2不再顺序覆盖同一字段，而是为每个工具定义联合最终状态：

- A001：目标单位在`m/s`之间歧义，两个候选都与`kg`量纲不兼容；
- A002：化学式在两个水合物表达式之间歧义，两个候选都超出中性式语法；
- A003：化学式在`SiO2/Al2O3`之间歧义，两个候选都超出冻结元素集；
- A004：组分在两个含负值向量之间歧义，两个候选都违反非负约束；
- B019：总体成分在`0.9/1.1`之间歧义，两个候选都超出给定二相连线或fraction范围。

这样，歧义和超域均可从最终模型输入观察。

## 4. 新增金标签可观察性门

候选规定：

```text
每个expected structural flag
必须可由
structured_state + versioned contract
重新计算

每个expected semantic flag
必须通过独立参考验证器
从最终structured_state + contract复核
```

v2审计结果：

| 检查 | 错配 |
|---|---:|
| 结构型标签可观察性 | 0/55 |
| 语义型标签参考复核 | 0/55 |
| 联合变换工具覆盖 | 5/5 |

人工逐题标签仍未进入真值链。

## 5. 双层门控职责

### 5.1 确定性结构层

输入：

```text
structured_state
versioned tool contract
```

规则：

- 任一`required_input`缺失 → `missing_parameter`；
- parameters中递归发现`status=ambiguous`且候选非空 → `ambiguous_parameter`；
- `service_status=unavailable` → `unavailable`；
- 请求版本与契约版本不一致 → `version_mismatch`。

检查器不读取：

- `mutation_types`；
- `expected_flags`；
- 任务ID；
- 变换历史。

### 5.2 LLM语义层

模型只允许输出：

```text
contract_defined_out_of_domain
contract_defined_unsupported_system
model_card_defined_ood
```

Schema禁止模型输出结构型flags、状态或动作。

### 5.3 合并与动作

```text
structural_flags ∪ semantic_flags
→ 按冻结flag顺序去重
→ e2-readiness-policy-v1.0.0
→ primary_status
→ call / clarify / refuse
```

模型无法覆盖或删除确定性结构层产生的flags。

## 6. 离线功能验证

为了只验证代码链，语义层使用oracle flags：

```text
真实确定性结构检查
+ oracle语义flags
→ 合并
→ 动作派生
```

结果：

| 指标 | 结果 |
|---|---:|
| 任务 | 55 |
| 结构flags完全匹配 | 55/55 |
| 合并flags完全匹配 | 55/55 |
| 动作正确 | 55/55 |
| 外部API调用 | 0 |

这些100%结果只证明：

1. 结构检查器符合规则；
2. 两层flags没有职责冲突；
3. 合并顺序正确；
4. 动作派生正确。

它们不证明LLM语义层达到100%，不能作为模型性能或方法效果结果。

## 7. 科学意义

该候选比“继续加强提示词”更符合项目主线：

1. 可程序验证的边界不交给概率模型反复猜测；
2. LLM集中处理需要理解契约含义的语义边界；
3. 每个动作均可追溯到具体flags及其来源层；
4. 可以做明确消融：

```text
LLM-only flags
vs
deterministic structural + LLM semantic
vs
oracle semantic upper bound
```

这能够直接检验双层门控是否降低提前调用、结构漏检和多标签遗漏。

## 8. 当前限制

当前仍不能把候选标记为通过：

- v2任务尚未进行模型语义层API开发复核；
- 尚无独立held-out E2任务；
- 尚未进行多次重复和波动估计；
- 温度范围、压力范围和模型卡OOD仍未覆盖；
- oracle离线集成不能替代真实模型结果；
- E2样本量尚未冻结。

## 9. 产物

可观察任务v2：

```text
outputs/v11_cf04_e2_pilot_v2_observable_candidate_20260731/
├── e2_pilot_tasks_v2.json
├── mutation_events_v2.json
├── observability_audit.json
└── artifact_manifest.json
```

双层门控候选：

```text
outputs/v11_cf04_e2_hybrid_gate_v1_candidate_20260731/
├── hybrid_policy_snapshot.json
├── semantic_prompt_snapshot.json
├── semantic_schema_snapshot.json
├── hybrid_gate_snapshot.py
├── v1_observability_defect_report.json
├── offline_pipeline_records.jsonl
├── offline_pipeline_report.json
├── candidate_report.json
└── artifact_manifest.json
```

## 10. 测试记录

本地测试均未执行外部API调用：

| 测试范围 | 结果 |
|---|---:|
| E2双层门控候选专项测试 | 8 passed |
| E2独立验证候选专项测试 | 8 passed |
| Core Freeze完整回归测试 | 153 passed |

## 11. 下一步

后续已完成：

1. v2通过复现性、哈希和标签可观察性复审，并锁定为开发源；
2. 构造40条独立语义验证候选；
3. 验证任务、基础任务组、边界值和最终可见状态均与开发集隔离；
4. 保持验证候选未执行、API未授权。

下一阶段应先在v2开发集完成语义提示词复核并冻结运行配置，再通过独立授权打开验证集。不能根据验证结果回改验证任务或提示词。
