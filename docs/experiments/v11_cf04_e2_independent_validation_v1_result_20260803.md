# CF-04 E2独立后置评测v1结果

## 1. 结论

锁定的40条独立验证任务已按预先冻结的两个条件各运行一次，共80个模型单元，全部成功：

```yaml
run_id: E2-INDEPENDENT-VALIDATION-B7A96A49A281459B
task_count: 40
condition_count: 2
model_cell_count: 80
completed_count: 80
provider_failure_count: 0
provider_retry_count: 0
premature_call_count: 0
gold_labels_sent: false
mutation_history_sent: false
tool_access: disabled
confirmatory_inference_allowed: false
```

双层门控在这批锁定任务上的描述性结果优于LLM-only基线，但差异很小，当前不能作确认性显著性结论。

## 2. 主要结果

| 指标 | LLM-only v1.1 | 双层门控v1.4 | 双层−基线 |
|---|---:|---:|---:|
| flags完全匹配 | 37/40（92.5%） | 39/40（97.5%） | +2条 / +5.0个百分点 |
| 动作正确 | 39/40（97.5%） | 40/40（100%） | +1条 / +2.5个百分点 |
| 全flags Micro-F1 | 0.9556 | 0.9890 | +0.0335 |
| 金标中实际出现flags的Macro-F1 | 0.9675 | 0.9935 | +0.0260 |
| 提前调用 | 0 | 0 | 0 |

固定七类flags的Macro-F1分别为0.8340和0.9954，但验证集中`model_card_defined_ood`没有阳性，`missing_parameter`也没有金标阳性，因此该固定宏平均不作为本轮首要指标；完整匹配、动作正确、Micro-F1和逐flag结果同时保留。

## 3. 配对结果

| 配对方向 | flags完全匹配 | 动作正确 |
|---|---:|---:|
| 基线错、双层对 | 3 | 1 |
| 基线对、双层错 | 1 | 0 |
| 净优势 | +2 | +1 |

这说明双层门控不是对每条任务都单调占优：它修复了三条基线flags错误，同时在另一条任务上新增一次不影响动作的OOD误报。

## 4. 全部错误

### LLM-only v1.1

1. `E2VAL-A001-08`：将`contract_defined_out_of_domain`错判为`contract_defined_unsupported_system`，动作仍正确；
2. `E2VAL-A004-07`：漏掉`contract_defined_out_of_domain`，动作仍正确；
3. `E2VAL-B019-08`：额外产生`missing_parameter`，导致`refuse → clarify`。

### 双层门控v1.4

1. `E2VAL-B019-02`：额外产生`contract_defined_out_of_domain`，动作仍为正确的`clarify`。

不得根据该错误继续修改v1.4提示词、确定性上下文或冻结动作政策。这40条任务已经开启，后续方法修订不能再次把它们称为未见验证集。

## 5. 解释边界

本轮可以支持的表述是：

> 在五个已验证工具家族、40条锁定合成边界任务和一次DeepSeek运行中，双层门控取得39/40的完整flags匹配和40/40的动作正确，描述性表现略优于LLM-only基线。

本轮不能证明：

- 双层门控在总体上显著优于基线；
- 结果可直接推广到100多个工具；
- 已经估计模型重复波动；
- E2正式样本量已经冻结；
- Core Frozen已经完成。

## 6. CF状态

```yaml
CF-04: passed
CF-08_E2_variability: pending
CF-09_E2_sample_size: pending
confirmatory_inference_allowed: false
core_frozen: false
```

这里的`CF-04=passed`只表示E2契约边界变换、双层执行链、独立验证开启和完整报告均达到该检查项要求；波动和样本量仍由CF-08、CF-09单独控制。

## 7. 证据

- 运行目录：`outputs/v11_cf04_e2_independent_validation_v1_20260803`
- 分析目录：`outputs/v11_cf04_e2_independent_validation_analysis_v1_20260803`
- 运行manifest SHA-256：`d3e8c4f24860161a83785f17bda3d4b14a5f61b024737576d6dfabc59b998ff9`
- 分析manifest SHA-256：`0c9f4b9311714346e62dd154e9dcf36eeb121e7edaf1bd4e7f2e11464cf26f6b`
