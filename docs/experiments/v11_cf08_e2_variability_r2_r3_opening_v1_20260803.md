# CF-08 E2 R2/R3重复波动开启包v1

## 1. 目的

CF-04的40条独立任务已经完成R1后置评测。CF-08需要估计相同模型、相同任务和相同冻结策略在不同运行重复下的波动，因此准备追加R2和R3：

```yaml
candidate_id: CF08-E2-VARIABILITY-R2-R3-OPENING-V1-20260803
status: prepared_not_authorized
task_count: 40
condition_count: 2
repeat_ids: [2, 3]
additional_repeat_count: 2
total_repeat_count_after_execution: 3
model_cell_count: 160
external_api_calls: 0
confirmatory_inference_allowed: false
core_frozen: false
```

该包没有执行新的DeepSeek调用。

## 2. 冻结范围

R2/R3完全复用R1：

- 同一40条已经开启的E2任务；
- 同一5个版本化工具契约；
- 同一`deepseek-v4-flash`；
- 同一`temperature=0.0`；
- 同一flags-only v1.1提示词与Schema；
- 同一hybrid v1.4提示词、Schema和非金标确定性上下文；
- 同一动作政策；
- 不调用冶金工具。

禁止根据R1结果修改提示词、确定性检查器、动作优先级或验证任务。

## 3. 统计单位

R2和R3是同一任务的重复观测，不是新增独立任务：

```yaml
repeat_units_are_independent_tasks: false
task_is_resampling_cluster: true
```

后续分析先在每个`task × condition`内比较R1/R2/R3，再汇总：

- flags预测三次完全一致的任务数；
- 动作预测三次完全一致的任务数；
- 完整匹配和动作正确结果的稳定任务数；
- 每个重复下的基线—双层门控配对差；
- 模型重复对结论方向的影响。

不能把120个“任务×重复”平铺成120个独立样本。

## 4. 防泄漏和执行闸门

开启包只包含验证候选manifest和R1结果manifest/报告，不复制或读取40条任务正文：

```yaml
held_out_task_content_read_by_builder: false
held_out_task_content_copied_into_opening: false
gold_labels_sent: false
mutation_history_sent: false
external_api_execution_authorized: false
external_api_calls: 0
```

执行器要求单独的R2/R3授权文件。授权缺失时，会在读取任务文件和建立API适配器之前失败。

## 5. 产物

```text
outputs/v11_cf08_e2_variability_r2_r3_opening_v1_20260803/
├── analyzer_snapshot.py
├── authorization_request_snapshot.json
├── opening_report.json
├── r1_analysis_manifest_snapshot.json
├── r1_analysis_report_snapshot.json
├── r1_run_manifest_snapshot.json
├── r1_run_report_snapshot.json
├── runner_snapshot.py
├── run_config_snapshot.json
├── validation_candidate_manifest_snapshot.json
└── artifact_manifest.json
```

开启包manifest SHA-256：

```text
5cea43af17560069a00c0c48193714d90753ce57591854ad91e25c23b7edae34
```

## 6. 当前限制

- R2/R3尚未授权或执行；
- 160个模型单元不是新增样本量；
- 即使三次重复稳定，也不能替代扩大独立任务数；
- CF-08 E2组件和CF-09 E2样本量继续保持`pending`；
- `core_frozen=false`。

## 7. 验证

| 范围 | 结果 |
|---|---:|
| R2/R3开启包专项测试 | 5 passed |
| Core Freeze完整回归 | 178 passed |
| 既有工具回归 | 99 passed，1 skipped |

全部测试均为本地执行；本轮新外部API调用为0。
