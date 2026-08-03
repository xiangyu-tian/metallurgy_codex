# CF-04 E2独立验证开启包v1

> 2026-08-03状态更新：该开启包随后获得一次性授权并已完成80个模型单元。下述`prepared_not_authorized`是开启包生成时的不可变状态；实际结果见`v11_cf04_e2_independent_validation_v1_result_20260803.md`。

## 1. 当前状态

v1.4开发晋级门已通过11/11项检查，独立验证执行器和授权请求已经冻结，但尚未获得执行授权：

```yaml
candidate_id: E2-INDEPENDENT-VALIDATION-OPENING-V1-20260803
status: prepared_not_authorized
task_count: 40
condition_count: 2
model_run_repeats: 1
model_cell_count: 80
external_api_calls: 0
validation_task_content_read_by_builder: false
validation_task_content_copied_into_opening: false
confirmatory_inference_allowed: false
core_frozen: false
```

开启包只复制验证候选manifest，不复制或读取40条任务内容。执行器会先验证独立授权文件，授权缺失时在读取任务文件之前失败。

## 2. 冻结比较

同一40条独立任务各运行两个条件：

| 条件 | 模型输出 | 后处理 |
|---|---|---|
| `flags_only_v1_1` | 全部边界flags | 冻结政策派生动作 |
| `hybrid_semantic_v1_4` | 语义flags | 确定性结构flags合并后由冻结政策派生动作 |

共同设置：

```yaml
provider: deepseek
model: deepseek-v4-flash
temperature: 0.0
repeats: 1
tool_access: disabled
gold_labels_sent: false
mutation_history_sent: false
```

首轮只做一次重复，用于独立后置评测和决定是否需要追加波动实验，不做确认性统计推断。

## 3. 发送边界

得到另行明确授权后，只允许发送：

- 40条锁定验证请求中的模型可见状态；
- 5个对应版本化工具契约视图；
- flags-only v1.1冻结提示词；
- hybrid v1.4冻结提示词及由请求和契约计算的非金标`deterministic_context`。

禁止发送：

- `expected_flags`、期望动作和其他金标；
- 变换历史；
- API凭据；
- 冶金工具输出；
- 40条候选以外的任务。

## 4. 防止结果后调参

验证集一旦开启：

- 不得根据验证结果修改v1.1或v1.4提示词、Schema、确定性检查器和动作政策；
- 必须保留并报告两条件全部成功、失败、重试和解析异常；
- 任何后续方法修订必须建立新的数据划分，不能重新使用这40条作为未见验证集。

## 5. 产物

```text
outputs/v11_cf04_e2_independent_validation_opening_v1_20260803/
├── authorization_request_snapshot.json
├── development_gate_manifest_snapshot.json
├── development_gate_snapshot.json
├── development_run_manifest_snapshot.json
├── opening_report.json
├── runner_snapshot.py
├── run_config_snapshot.json
├── validation_candidate_manifest_snapshot.json
└── artifact_manifest.json
```

开启包manifest SHA-256：

```text
a71f3749feb97ae27ceee2e3f94731d869c60b8fb5b2160a14985363cbc875cc
```

## 6. 下一授权边界

下一次若执行独立验证，需要用户明确同意：

1. 推送本轮v1.4结果和该未授权开启包；
2. 将锁定40条任务的非金标模型可见状态、5个契约视图及两套冻结提示词发送至DeepSeek；
3. 使用`deepseek-v4-flash`执行两条件各一次，共80个模型单元；
4. 不调用冶金工具，并承诺验证开启后不再依据结果修改冻结策略。

本文件和当前开启包本身不构成上述授权。
