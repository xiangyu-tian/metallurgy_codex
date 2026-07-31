# CF-04 E2双层门控语义开发复核v1.1结果

## 1. 结论

本次单次开发复核已按授权完成，但未通过冻结晋级门：

```yaml
run_id: E2-HYBRID-SEMANTIC-DEV-F3BA521A42AF4CCD
task_count: 55
completed_count: 55
provider_failure_count: 0
development_gate:
  passed_check_count: 8
  required_check_count: 11
  decision: revise_on_development_only
validation_dataset_access_count: 0
validation_dataset_may_be_opened: false
confirmatory_inference_allowed: false
core_frozen: false
```

因此，40条独立验证候选继续密封。该结果只能用于开发集内诊断和修订，不能形成模型性能结论。

## 2. 主要指标

| 指标 | 观察值 | 门槛 | 结果 |
|---|---:|---:|---|
| 完成任务数 | 55 | 55 | 通过 |
| 供应商失败数 | 0 | 0 | 通过 |
| 语义Schema有效数 | 55 | 55 | 通过 |
| 结构标志精确数 | 55 | 55 | 通过 |
| 语义标志宏F1 | 0.8295 | ≥0.90 | 未通过 |
| 合并标志精确数 | 45 | ≥52 | 未通过 |
| 动作正确数 | 54 | ≥53 | 通过 |
| OOD召回率 | 1.0000 | ≥0.90 | 通过 |
| 不支持系统召回率 | 0.8333 | ≥0.90 | 未通过 |
| 过早调用数 | 0 | ≤1 | 通过 |
| 验证集访问数 | 0 | 0 | 通过 |

## 3. 错误模式

55条中有10条语义标志不完全一致，全部涉及`contract_defined_out_of_domain`：

- A001有2条：目标单位缺失或显式歧义时，模型额外输出OOD；动作仍由结构层正确保持为`clarify`。
- B019有8条：
  - 7条在没有OOD金标时额外输出OOD；
  - 1条显式`requested_phase_count=3`应为`contract_defined_unsupported_system`，模型却输出OOD；
  - 其中B019正常可调用任务被错误拒绝，构成本次唯一动作错误。

按工具汇总：

| 工具 | 任务数 | 语义精确数 | 主要模式 |
|---|---:|---:|---|
| A001 | 12 | 10 | 将结构不完整升级为语义越界 |
| A002 | 10 | 10 | 无误差 |
| A003 | 10 | 10 | 无误差 |
| A004 | 10 | 10 | 无误差 |
| B019 | 13 | 5 | 将三个组成标量误解为三组元，并混淆不支持系统与OOD |

## 4. 根因判断

根因定位在“结构化请求到契约语义的映射规则”，而不是：

- 输出Schema：55/55有效；
- 确定性结构检查：55/55精确；
- 合并和动作策略：确定性执行；
- 供应商稳定性：0次失败、0条重试；
- 验证集泄漏：访问数为0。

基于错误分布作出的开发性推断是：

1. v1提示词只说明结构检查器已经处理缺参和歧义，但没有明确禁止“因字段不完整而推断语义越界”；
2. v1提示词没有明确区分“组成标量参数的数量”和“热力学组元数”，导致B019系统性误读；
3. v1提示词虽然定义了不支持系统，但没有规定显式相数/组元数不匹配相对OOD的分类优先级。

模型没有输出自然语言解释，所以上述根因是由跨任务一致错误模式支持的诊断推断，而不是模型自述。

## 5. v1.2最小修订

v1.2只补充三条证据规则，不调整数据、金标、冻结门槛或动作策略：

1. 缺失或显式歧义字段只由结构层处理，不能仅据此生成语义flag；
2. 不得从参数字段数量或组成标量数量推断组元数或相数；
3. 显式系统、相数或组元数不匹配优先归类为`contract_defined_unsupported_system`。

新的未授权开启包仍绑定：

- 同一55条开发任务；
- 同一5个工具契约；
- 同一输出Schema和双层门控；
- 同一11项晋级门；
- 单次运行；
- 工具访问关闭；
- 40条独立验证集禁止访问。

## 6. 证据位置

- 运行结果：`outputs/v11_cf04_e2_hybrid_semantic_development_v1_1_20260731`
- 门控分析：`outputs/v11_cf04_e2_hybrid_semantic_development_analysis_v1_1_20260731`
- v1.2提示词：`Tools/core_freeze/e2_contract_boundaries/prompts_hybrid_semantic_v1_2.json`
- v1.2未授权开启包：`outputs/v11_cf04_e2_hybrid_semantic_dev_opening_v1_2_20260731`
