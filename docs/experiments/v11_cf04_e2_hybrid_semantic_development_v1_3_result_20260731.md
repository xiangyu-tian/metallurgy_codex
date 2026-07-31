# CF-04 E2双层门控语义开发复核v1.3结果

## 1. 结论

v1.3完成55条单次开发复核，11项晋级检查通过10项，但仍未达到完整晋级标准：

```yaml
run_id: E2-HYBRID-SEMANTIC-DEV-9D67593DA79A4522
completed_count: 55
provider_failure_count: 0
semantic_supported_flag_macro_f1: 0.9166666666666667
merged_flags_exact_count: 49
action_correct_count: 54
out_of_domain_recall: 1.0
unsupported_system_recall: 1.0
premature_call_count: 0
validation_dataset_access_count: 0
gate_checks_passed: 10
gate_checks_required: 11
decision: revise_on_development_only
```

唯一失败项为：

```text
merged_flags_exact_count = 49 < 52
```

40条独立验证候选继续密封。

## 2. 三版趋势

| 指标 | v1.1 | v1.2 | v1.3 |
|---|---:|---:|---:|
| 语义宏F1 | 0.8295 | 0.7750 | 0.9167 |
| 合并标志精确数 | 45 | 48 | 49 |
| 动作正确数 | 54 | 55 | 54 |
| OOD召回率 | 1.0000 | 0.6000 | 1.0000 |
| unsupported召回率 | 0.8333 | 1.0000 | 1.0000 |
| 通过晋级检查 | 8/11 | 8/11 | 10/11 |

v1.3已解决v1.2的漏报和unsupported混淆，但恢复了B019的6个OOD误报。

## 3. 剩余六条误差

六条全部来自B019：

- 正常可调用任务被额外标记OOD；
- 缺参任务被额外标记OOD；
- `[0.4, 40.0]`歧义候选中存在合法候选，仍被标记OOD；
- 显式不支持系统任务同时多报OOD；
- 缺少组成基准任务被额外标记OOD；
- `fraction/percent`两个合法基准候选仍被标记OOD。

其中正常任务的误报造成唯一动作错误：`call → refuse`。

## 4. 根因判断

v1.1和v1.3在B019上出现相同的系统性误报，而v1.2虽然消除误报，却通过过度屏蔽造成真实OOD漏报。这表明继续增加自然语言禁令不能稳定解决问题。

根因位于双层门之间的载荷契约：

- LLM只看到原始参数JSON；
- `verification_scope.component_count=2`与三个组成标量同时出现；
- 结构层已经知道哪些字段缺失或歧义，却没有把这一确定性状态传给语义层；
- 请求是否显式声明系统、相数或组元数也没有提供机器可读的匹配状态。

因此，v1.4不再仅修改提示词，而增加不含金标的`deterministic_context`。

## 5. v1.4架构修订

语义层新增以下确定性输入：

```text
structural_flags
missing_required_inputs
ambiguous_parameter_paths
explicit_domain_evidence.requested_system
explicit_domain_evidence.requested_phase_count
explicit_domain_evidence.requested_component_count
parameter_field_count_is_domain_count = false
```

这些字段只由请求和工具契约计算，不读取：

- `expected_flags`；
- 期望动作；
- 变换类型；
- 任务ID；
- 40条验证集。

任务、金标、模型、输出Schema、动作策略和11项晋级门保持不变。

## 6. 证据位置

- v1.3运行：`outputs/v11_cf04_e2_hybrid_semantic_development_v1_3_20260731`
- v1.3门控：`outputs/v11_cf04_e2_hybrid_semantic_development_analysis_v1_3_20260731`
- v1.4开启包：`outputs/v11_cf04_e2_hybrid_semantic_dev_opening_v1_4_20260731`
