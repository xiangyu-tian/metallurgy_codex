# CF-04 E2双层门控语义开发复核v1.2结果

## 1. 结论

v1.2单次开发复核完整执行，但仍未通过冻结晋级门：

```yaml
run_id: E2-HYBRID-SEMANTIC-DEV-023291404A0C453D
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

40条独立验证候选继续密封。

## 2. 指标与v1.1比较

| 指标 | v1.1 | v1.2 | v1.2门槛 | 结果 |
|---|---:|---:|---:|---|
| 语义Schema有效数 | 55 | 55 | 55 | 通过 |
| 结构标志精确数 | 55 | 55 | 55 | 通过 |
| 语义标志宏F1 | 0.8295 | 0.7750 | ≥0.90 | 未通过 |
| 合并标志精确数 | 45 | 48 | ≥52 | 未通过 |
| 动作正确数 | 54 | 55 | ≥53 | 通过 |
| OOD召回率 | 1.0000 | 0.6000 | ≥0.90 | 未通过 |
| 不支持系统召回率 | 0.8333 | 1.0000 | ≥0.90 | 通过 |
| 过早调用数 | 0 | 0 | ≤1 | 通过 |

v1.2消除了全部OOD误报，使动作达到55/55；但同时漏掉6个真实OOD，并产生3个unsupported误报。总体上属于过度纠偏，不能晋级。

## 3. 七条语义误差

| 任务 | 结构/场景 | 期望语义 | v1.2语义 |
|---|---|---|---|
| E2V2-A001-11 | 歧义候选均为跨量纲单位 | OOD | 空 |
| E2V2-A001-12 | 跨量纲单位＋服务不可用 | OOD | unsupported |
| E2V2-A002-09 | 歧义候选均超出化学式语法 | OOD | unsupported |
| E2V2-A002-10 | 超出语法＋服务不可用 | OOD | 空 |
| E2V2-A004-09 | 歧义候选均含负组成 | OOD | 空 |
| E2V2-B019-08 | 缺少组成基准 | 空 | unsupported |
| E2V2-B019-13 | 总体组成超出相端点＋服务不可用 | OOD | 空 |

## 4. 根因判断

v1.2的三个新规则解决了v1.1的误报，但其中两处表达过宽：

1. “缺失或显式歧义字段暂不判断越界”掩盖了候选值本身仍然可观察的多标签任务；
2. 没有明确声明服务不可用和版本错配不能抑制其他独立语义证据；
3. “显式系统/相数/组元数不匹配”缺少字段级证据限制，模型把单位、语法或缺少组成基准也归为unsupported。

这一判断来自七条误差的共同结构和v1.1→v1.2的16条预测变化。模型仍只输出flags，因此属于开发性模式推断，不是模型自述。

## 5. v1.3最小修订

v1.3不改变数据、金标、门槛或双层架构，只修订语义证据规则：

1. 结构型和语义型flags相互独立，可以同时成立；
2. 字段缺失本身不产生语义证据，但不能掩盖其他完整字段；
3. 歧义候选全部违反同一边界时保留语义flag；
4. 服务不可用或版本错配不停止语义判断；
5. unsupported只由`request_context`中的显式系统、相数或组元数不匹配触发；
6. 参数值、单位、语法、元素集、组成范围和verification scope违反仍归OOD。

v1.3当前仅为未授权开发开启包，不允许新的API调用。

## 6. 证据位置

- v1.2运行结果：`outputs/v11_cf04_e2_hybrid_semantic_development_v1_2_20260731`
- v1.2门控分析：`outputs/v11_cf04_e2_hybrid_semantic_development_analysis_v1_2_20260731`
- v1.3提示词：`Tools/core_freeze/e2_contract_boundaries/prompts_hybrid_semantic_v1_3.json`
- v1.3未授权开启包：`outputs/v11_cf04_e2_hybrid_semantic_dev_opening_v1_3_20260731`
