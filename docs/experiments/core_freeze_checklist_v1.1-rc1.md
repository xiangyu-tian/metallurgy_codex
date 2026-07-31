# Core Frozen 证据检查清单 v1.1

## 文档状态

- 版本：`1.1-rc1`
- 日期：2026-07-31
- 适用协议：`research_protocol_v1.1-rc1`
- 配套数据规范：`dataset_executable_reference_policy_v1.0-rc1`
- 当前阶段：可执行真值主线验证
- Core Frozen：`false`

本清单替代 `core_freeze_checklist_v1.0.md` 对当前 v1.1 主线的治理作用。v1.0 清单继续作为历史记录保留，但其中依赖专家逐题金标准的 CF-01、CF-02、CF-03 和 CF-05 不能用于决定 v1.1 是否冻结。

## 1. 编号迁移原则

v1.1 的 CF 编号重新绑定到可执行真值冻结门槛：

- 不把 AI-A、AI-B 共识或单人裁决升级为确认性金标准；
- 不要求专家逐题自由判断作为正式实验启动条件；
- 不把 120 个 Schema-only 工具称为 120 个已验证计算引擎；
- 正式真值只来自 G1、G2 和 C1；
- 旧 Track A 银标保留作探索和错误发现；
- 旧 Track B 模板保留作自然任务种子，不直接提供正式可接受工具集合。

旧、新编号语义不同，不得把旧清单状态直接复制到本清单。

## 2. 状态定义

- `pending`：尚未开始；
- `in_progress`：已有证据，但未达到全部验收门槛；
- `passed`：机器可复核证据完整并达到门槛；
- `failed`：已执行但未达到门槛；
- `waived`：有书面理由、影响分析和项目审批的正式豁免。

## 3. v1.1 Core Freeze总门槛

| ID | 冻结证据 | 最低验收标准 | 当前状态 | 当前证据与缺口 |
|---|---|---|---|---|
| CF-01 | 协议与数据规范兼容性 | v1.1研究问题、G1/G2/C1真值、S1限制、数据生产和`core_frozen=false`一致 | `passed` | `outputs/v11_cf01_cf02_audit_20260731/`；8项兼容性检查全部通过 |
| CF-02 | `verified_core`工具及独立参考 | 至少3个工具；契约字段、来源、适用域、限制、哈希、正常/边界案例和独立参考均通过 | `passed` | A001、A002、A003、A004、B019共5工具；27/27参考案例通过；11项审计检查通过 |
| CF-03 | E1b基础任务与收益先导 | 基础任务、独立参考、No Tool/Forced Tool对照、重复和防循环划分可复现 | `passed` | 候选证据审计通过；E1b的120基础任务组、240任务和3次重复设计已审批冻结 |
| CF-04 | E2契约边界变换 | 缺参、歧义、契约超域、不支持、不可用和版本错配可由规则复算；多标签与动作优先级测试通过 | `in_progress` | 双层门控v1.1开发复核完成但仅通过8/11项晋级检查；40条验证集保持密封；已形成v1.2未授权开发开启包 |
| CF-05 | E3参数、可接受工具与契约近邻 | 参数规范化、单一/等价可接受工具、0/4/8契约近邻和嵌套池测试通过 | `in_progress` | 五工具端到端选择已验证；17/50/100/120契约目录与近邻生成仍未完成 |
| CF-06 | 17/50/100/120 Schema API可行性 | 实测函数数量、Token、上下文、延迟、错误、`tool_choice=none`和供应商限制 | `pending` | 尚未按v1.1 Schema-only目录口径执行 |
| CF-07 | 数据层级与泄漏审计 | `controlled_confirmatory`、`naturalistic_validation`、`exploratory_domain_cases`分层；家族划分和收益校准/评价隔离通过 | `in_progress` | E1b/E1c受控集已分区；自然验证层和探索层尚未冻结 |
| CF-08 | 先导波动与功效分析 | 估计任务家族、工具家族、重复波动和主要效应；固定正式重复次数 | `in_progress` | E1b组件已批准：5个百分点最小效应、80%功效、120基础任务组、3次重复；E1a/E2/E3组件待各自先导 |
| CF-09 | 样本量附录 | 生成并审批v1.1样本量和重复次数附录 | `in_progress` | `sample_size_addendum_v1.1-rc1.md`已建立，E1b章节批准；E1a/E2/E3章节待补 |
| CF-10 | 新统计接口与报告模板干跑 | v1.1 E1/E2/E3字段通过输入校验、聚合、Bootstrap/GLMM和报告模板干跑 | `in_progress` | 旧CF-11基础设施已完成；尚未使用v1.1真实候选数据干跑 |
| CF-11 | 正式资产哈希冻结 | 工具、契约、生成器、任务、参考结果、评分器、配置和报告模板全部进入不可变manifest | `in_progress` | verified_core、E1b、E1c已有局部manifest；全项目冻结清单尚未形成 |
| CF-12 | 最终审查与冻结决定 | CF-01至CF-11全部`passed`或正式`waived`；限制声明、偏离记录和项目审批完整 | `pending` | `core_frozen=false` |

只有 CF-01 至 CF-11 全部为 `passed` 或具有正式 `waived`，且 CF-12 完成最终审查后，才能把 v1.1 状态改为：

```text
core_frozen = true
```

## 4. CF-01验收记录

```yaml
check_id: CF-01
title: v1.1协议与可执行数据规范兼容性
status: passed
audit_id: V11-CF01-CF02-AUDIT-20260731
evidence:
  - outputs/v11_cf01_cf02_audit_20260731/audit_report.json
  - outputs/v11_cf01_cf02_audit_20260731/artifact_manifest.json
  - Tools/core_freeze/audit_v11_cf01_cf02.py
acceptance_result:
  compatibility_checks: 8/8
  formal_truth_tiers: [G1, G2, C1]
  provisional_silver_promoted: false
  legacy_track_a_gold_reused: false
scope:
  - 仅证明协议、数据规范和真值治理一致
  - 不代表后续实验或Core Frozen通过
```

冻结源文件：

| 文件 | SHA-256 |
|---|---|
| `research_protocol_v1.1-rc1.md` | `14e219ddd9b9891f338845376d46f9442794b474421bda9d18fa1e8796712d25` |
| `dataset_executable_reference_policy_v1.0-rc1.md` | `4984dc17e65bda9d0250b8e8c199573bfc2abdee70091258c858d0be9ca01d8d` |
| `research_protocol_revision_rationale_20260730.md` | `264e6acf9a382982dc6b42a7d8e6d6cb47c652f82aecda5a65b2fbf19dbc900c` |

## 5. CF-02验收记录

```yaml
check_id: CF-02
title: 至少3个verified_core工具及独立参考验证
status: passed
audit_id: V11-CF01-CF02-AUDIT-20260731
verified_tools: [A001, A002, A003, A004, B019]
verified_tool_count: 5
reference_case_count: 27
passed_reference_case_count: 27
failed_reference_case_count: 0
normal_boundary_coverage: passed
published_manifest_verified: true
core_frozen: false
scope:
  - 只接受五个工具各自verification_scope内的结论
  - 不覆盖其余12个已实现工具
  - 不覆盖103个规划工具
  - 不证明120工具均可执行
```

冻结源文件：

| 文件 | SHA-256 |
|---|---|
| `tool_contract.schema.json` | `349ac1033c8d2e03a297ef3e88ccacf7ad05e5d8f66fc1bd2ae73df90afcd3ca` |
| `contracts_v1.json` | `9df57db7836dbcb24d5b5d7f5b487003ade3a33955d01e2a827633aaa14fc0ec` |
| `reference_cases_v1.json` | `8efabe718a67e34d471921735461f654d5541559dbe5e322b7172d0250367d1f` |
| `validate_verified_core.py` | `6b0a342bb7a53876b849d76fca3bf1243a8436d2a58d70965a8cfe6cad16cd4c` |
| 已发布验证报告 | `9b50c51f79370316544ef0c226ea88e98c3c0eda76a03919afb1b77a0b657341` |
| 已发布manifest | `e61f0f909fda929c4fd5b59031c046009aa2c797e52ab102e97bf7d0e6fa7058` |

## 6. CF-03验收记录

```yaml
check_id: CF-03
title: E1b基础任务、收益先导与防循环划分
status: passed
audit_id: V11-CF03-CANDIDATE-AUDIT-20260731
candidate_evidence_status: passed
evidence:
  - outputs/v11_cf03_candidate_20260731/cf03_audit_report.json
  - outputs/v11_cf03_candidate_20260731/benefit_evidence_registry.json
  - outputs/v11_cf03_candidate_20260731/power_input.json
  - outputs/v11_cf03_candidate_20260731/artifact_manifest.json
  - Tools/core_freeze/audit_v11_cf03.py
acceptance_result:
  verified_tools: [A001, A002, A003, A004, B019]
  benefit_tasks: 45
  benefit_base_task_groups: 26
  benefit_paired_repeats: 135
  gate_tasks: 27
  gate_base_task_groups: 16
  gate_paired_repeats: 81
  pilot_model_run_repeats: 3
  task_id_overlap: 0
  task_pair_id_overlap: 0
  base_task_group_id_overlap: 0
  pilot_results_promoted_to_confirmatory: false
  tool_benefit_written_back_to_base_truth: false
resolved_requirements:
  - CF-08 E1b功效参数已审批
  - 正式模型重复次数冻结为3
  - CF-09附录的E1b章节已审批
formal_design:
  base_task_groups: 120
  task_count: 240
  model_run_repeats: 3
  model_cell_count: 1440
core_frozen: false
```

E1b收益校准集用于估计先导效应，独立门控集用于检验冻结策略；E1c只登记为机制层次的次要证据，不与E1b主要收益效应合并。项目负责人批准正式功效参数后，CF-03的候选证据、功效依据和重复次数门槛均已满足。

## 7. CF-08/CF-09 E1b组件冻结记录

```yaml
finalization_id: V11-CF08-CF09-E1B-FINAL-20260731
approval_id: V11-CF08-E1B-APPROVAL-20260731
approval_scope: E1b formal benefit experiment only
evidence:
  - Tools/core_freeze/approvals/v11_cf08_e1b_approval_20260731.json
  - docs/experiments/sample_size_addendum_v1.1-rc1.md
  - outputs/v11_cf08_cf09_e1b_final_20260731/e1b_design_finalization.json
  - outputs/v11_cf08_cf09_e1b_final_20260731/cf09_coverage_report.json
  - outputs/v11_cf08_cf09_e1b_final_20260731/artifact_manifest.json
approved_parameters:
  minimum_meaningful_accuracy_gain: 0.05
  alpha: 0.05
  test_direction: one_sided_positive_gain
  target_power: 0.80
  base_task_groups: 120
  task_count: 240
  model_run_repeats: 3
  model_cell_count: 1440
status:
  cf03: passed
  cf08_e1b_component: passed
  cf08_overall: in_progress
  cf09_e1b_component: passed
  cf09_overall: in_progress
core_frozen: false
```

CF-08和CF-09是全项目门槛。E1b组件通过不能替代E1a、E2和E3各自的样本量依据，因此两项总体状态仍为`in_progress`。

## 8. 旧CF-01/CF-02资产的保留方式

### AI辅助Track A

`track_a_provisional_silver.json`继续保留：

```text
label_tier = provisional_silver
formal_cf01_eligible = false
formal_cf03_eligible = false
```

用途仅限：

- 发现标签体系歧义；
- 提供自然表达种子；
- 记录未来需要领域复核的案例；
- 作为探索性对照。

### Track B模板

旧20任务模板继续保留为自然任务和路由错误分析种子。未经契约自动匹配和等价验证，不得将其中人工填写的：

- `acceptable_tools`；
- `unacceptable_near_neighbors`；
- `similarity_ratings`；

称为v1.1确认性金标准。

## 9. 下一执行点

CF-09的E1b章节已冻结，但全项目附录仍缺E1a、E2和E3。下一执行点不是立即运行1,440个E1b正式模型单元，而是补齐其余实验的前置先导：

1. 推进CF-04，生成E2契约边界变换和先导波动；
2. 继续CF-05/CF-06，完成E3近邻工具池及Schema API先导；
3. 固定E1a正式条件并执行Schema暴露先导；
4. 将E1a、E2和E3功效结果补入样本量附录；
5. 全部章节审批后再把CF-08、CF-09改为`passed`。

## 10. CF-04候选证据记录

```yaml
check_id: CF-04
audit_id: V11-CF04-E2-PILOT-AUDIT-20260731
status: in_progress
candidate_evidence_status: passed
dataset_id: E2-CONTRACT-BOUNDARY-PILOT-V1-20260731
evidence:
  - Tools/core_freeze/e2_contract_boundaries/policy_v1.json
  - Tools/core_freeze/e2_contract_boundaries/build_e2_pilot.py
  - outputs/v11_cf04_e2_pilot_20260731/e2_pilot_tasks.json
  - outputs/v11_cf04_e2_pilot_20260731/mutation_events.json
  - outputs/v11_cf04_e2_pilot_20260731/coverage_report.json
  - outputs/v11_cf04_e2_pilot_20260731/audit_report.json
  - outputs/v11_cf04_e2_pilot_20260731/artifact_manifest.json
summary:
  tool_count: 5
  task_count: 55
  ready_task_count: 5
  mutated_task_count: 50
  multi_label_task_count: 15
  mutation_event_count: 65
  action_counts:
    call: 5
    clarify: 24
    refuse: 26
human_per_task_labels_used: false
coverage_gaps:
  - out_of_temperature_range
  - out_of_pressure_range
  - model_card_defined_ood
pending:
  - 引入声明温度范围的verified_core契约
  - 引入声明压力范围的verified_core契约
  - 引入带模型卡OOD边界的verified神经网络工具
  - 经单独授权执行双层门控LLM语义层v1.2开发复核
  - 冻结模型、提示词、Schema和运行参数
  - 单独授权并开启40条独立语义验证候选
  - 比较LLM-only与双层门控并估计模型重复波动
model_pilot:
  execution_status: completed
  run_id: E2-DEV-RUN-113954B8E81F4D86
  task_count: 55
  provider_failure_count: 0
  strict_schema_valid_rate: 0.23636363636363636
  strict_flags_exact_accuracy: 0.2
  diagnostic_flags_exact_accuracy: 0.7636363636363637
  diagnostic_raw_action_accuracy: 0.8909090909090909
  confirmatory_inference_allowed: false
policy_v1_1_candidate:
  status: development_recheck_completed_with_limitations
  model_output_fields:
    - flags
  derived_fields:
    - primary_status
    - action
  counterfactual_replay_schema_valid_rate: 1.0
  counterfactual_replay_flags_exact_accuracy: 0.7636363636363637
  counterfactual_replay_action_accuracy: 0.9090909090909091
  new_provider_calls: 55
  independent_model_recheck: completed
  recheck_run_id: E2-DEV-V11-RUN-876742250AA34387
  recheck_schema_valid_rate: 1.0
  recheck_flags_exact_accuracy: 0.8727272727272727
  recheck_supported_flag_macro_f1: 0.9457680250783699
  recheck_multilabel_flags_exact_accuracy: 0.6
  recheck_action_accuracy: 0.8909090909090909
  recheck_clarify_action_accuracy: 0.75
  recheck_invalid_execution_rate: 0.02
  recheck_premature_call_rate: 0.041666666666666664
  development_gate:
    schema_valid_rate_100_percent: passed
    unsupported_system_recall_improved: passed
    multilabel_exact_accuracy_improved: passed
    clarify_action_accuracy_improved: failed
  confirmatory_inference_allowed: false
label_observability_correction:
  source_dataset: E2-CONTRACT-BOUNDARY-PILOT-V1-20260731
  defect_status: confirmed
  unobservable_gold_task_count: 4
  affected_tasks:
    - E2P-A001-11
    - E2P-A002-09
    - E2P-A003-09
    - E2P-B019-12
  corrected_dataset: E2-CONTRACT-BOUNDARY-PILOT-V2-CANDIDATE-20260731
  corrected_structural_observability_mismatch_count: 0
  corrected_semantic_observability_mismatch_count: 0
hybrid_gate_v1_candidate:
  status: local_candidate_prepared_not_authorized
  deterministic_structural_flags:
    - missing_parameter
    - ambiguous_parameter
    - unavailable
    - version_mismatch
  llm_semantic_flags:
    - contract_defined_out_of_domain
    - contract_defined_unsupported_system
    - model_card_defined_ood
  offline_oracle_pipeline:
    structural_exact_accuracy: 1.0
    merged_exact_accuracy: 1.0
    action_accuracy: 1.0
    oracle_semantic_flags_used: true
    model_performance_claim_allowed: false
  external_api_calls: 0
  external_api_execution_authorized: false
  confirmatory_inference_allowed: false
e2_v2_development_source_review:
  decision: accepted_as_locked_development_source_for_validation
  task_count: 55
  mutation_event_count: 65
  manifest_hashes_valid: true
  stored_artifacts_match_rebuild: true
  label_observability_mismatch_count: 0
  scope_limit: development_source_lock_only
independent_semantic_validation_v1:
  dataset_id: E2-INDEPENDENT-SEMANTIC-VALIDATION-V1-CANDIDATE-20260731
  status: locked_validation_candidate_not_executed
  task_count: 40
  semantic_positive_count: 20
  semantic_negative_count: 20
  multi_label_count: 10
  development_state_overlap_count: 0
  observability_error_count: 0
  external_api_calls: 0
  external_api_execution_authorized: false
  model_performance_claim_allowed: false
  confirmatory_inference_allowed: false
hybrid_semantic_development_opening_v1:
  candidate_id: E2-HYBRID-SEMANTIC-DEV-OPENING-V1-20260731
  status: superseded_before_execution
  source_dataset: E2-CONTRACT-BOUNDARY-PILOT-V2-CANDIDATE-20260731
  task_count: 55
  model_output_fields:
    - semantic_flags
  model_payload_leakage_error_count: 0
  gold_labels_sent: false
  mutation_history_sent: false
  validation_dataset_sent: false
  external_api_calls: 0
  external_api_execution_authorized: false
  confirmatory_inference_allowed: false
hybrid_semantic_development_opening_v1_1:
  candidate_id: E2-HYBRID-SEMANTIC-DEV-OPENING-V1.1-20260731
  status: executed_gate_failed
  source_dataset: E2-CONTRACT-BOUNDARY-PILOT-V2-CANDIDATE-20260731
  task_count: 55
  advancement_gate_id: E2-HYBRID-SEMANTIC-DEVELOPMENT-GATE-V1
  advancement_required_check_count: 11
  advancement_partial_pass_allowed: false
  merged_flags_exact_minimum: 52
  action_correct_minimum: 53
  semantic_macro_f1_minimum: 0.9
  premature_call_maximum: 1
  validation_dataset_access_count: 0
  external_api_calls: 55
  external_api_execution_authorized: true
  confirmatory_inference_allowed: false
hybrid_semantic_development_result_v1_1:
  run_id: E2-HYBRID-SEMANTIC-DEV-F3BA521A42AF4CCD
  completed_count: 55
  provider_failure_count: 0
  structural_flags_exact_count: 55
  semantic_supported_flag_macro_f1: 0.8295454545454546
  merged_flags_exact_count: 45
  action_correct_count: 54
  premature_call_count: 0
  validation_dataset_access_count: 0
  advancement_checks_passed: 8
  advancement_checks_required: 11
  decision: revise_on_development_only
  validation_dataset_may_be_opened: false
hybrid_semantic_development_opening_v1_2:
  candidate_id: E2-HYBRID-SEMANTIC-DEV-OPENING-V1.2-20260731
  status: prepared_not_authorized
  revision_scope:
    - structural incompleteness is not semantic OOD evidence
    - scalar parameter count is not component or phase count
    - explicit system/count mismatch maps to unsupported-system
  source_dataset: E2-CONTRACT-BOUNDARY-PILOT-V2-CANDIDATE-20260731
  task_count: 55
  advancement_gate_id: E2-HYBRID-SEMANTIC-DEVELOPMENT-GATE-V1
  external_api_calls: 0
  external_api_execution_authorized: false
  validation_dataset_access: forbidden
  confirmatory_inference_allowed: false
core_frozen: false
```
