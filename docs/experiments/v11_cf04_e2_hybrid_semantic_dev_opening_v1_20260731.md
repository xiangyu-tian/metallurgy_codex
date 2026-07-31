# v1.1 CF-04 E2双层门控语义层开发复核开启包

> 后续状态：该开启包在任何外部执行前由v1.1取代。v1产物保持不变，`external_api_calls=0`。

## 结论

E2双层门控的LLM语义层开发复核开启包已经生成，但尚未获得外部执行授权：

```text
candidate_id = E2-HYBRID-SEMANTIC-DEV-OPENING-V1-20260731
dataset_id = E2-CONTRACT-BOUNDARY-PILOT-V2-CANDIDATE-20260731
task_count = 55
status = prepared_not_authorized
external_api_calls = 0
```

运行器在授权文件不存在时，会在创建API适配器和发送请求之前拒绝执行。

## 1. 本次准备的实验

待授权实验只评价LLM语义层：

```text
模型输入：
版本化工具契约视图
+ 最终structured_state

模型输出：
semantic_flags

确定性程序负责：
structural_flags
→ flags合并
→ primary_status
→ call / clarify / refuse
```

模型允许输出的字段只有：

```text
semantic_flags
```

允许的语义标签只有：

- `contract_defined_out_of_domain`
- `contract_defined_unsupported_system`
- `model_card_defined_ood`

## 2. 冻结运行参数

```text
provider = deepseek
model = deepseek-v4-flash
endpoint = https://api.deepseek.com
temperature = 0.0
thinking = disabled
max_tokens = 192
repeats = 1
tool_access = disabled
validation_dataset_access = forbidden
```

API密钥只允许在未来执行时从`DEEPSEEK_API_KEY`环境变量读取，不进入配置、开启包或Git产物。

## 3. 外发范围

未来只有在用户明确授权后，才允许发送：

1. 55条合成E2 v2开发任务的最终结构化状态；
2. 对应的5个版本化工具契约视图；
3. 冻结的语义层提示词。

明确不发送：

- 40条独立验证候选；
- `expected_flags`等金标签；
- `mutation_types`及变换历史；
- 任务ID、基础任务ID和任务组ID；
- API凭据；
- 冶金工具输出。

## 4. 模型可见载荷审计

55条待执行载荷已经逐条生成并检查：

| 检查 | 结果 |
|---|---:|
| 待执行载荷 | 55 |
| 禁止字段泄漏 | 0 |
| 任务标识符泄漏 | 0 |
| 金标签发送 | 否 |
| 变换历史发送 | 否 |
| 独立验证集发送 | 否 |

开启包只记录每条载荷的SHA-256，不记录模型结果。

## 5. 授权门

当前仅存在：

```text
execution_authorization_request_hybrid_semantic_v1.json
```

不存在：

```text
execution_authorization_hybrid_semantic_development_v1.json
```

未来授权记录必须精确绑定：

- 运行配置ID；
- 数据集ID及任务数；
- 端点和模型；
- 任务、提示词、Schema、配置和运行器哈希；
- 只执行一次；
- 禁止访问独立验证集；
- 禁止调用冶金工具。

普通命令行参数不能绕过该授权文件。

## 6. 离线测试

使用本地假适配器和Oracle语义标签只验证程序链路：

```text
semantic schema
→ semantic flags评分
→ deterministic structural flags
→ ordered merge
→ frozen action policy
```

专项测试结果：

```text
8 passed
```

Core Freeze完整回归：

```text
161 passed
```

Oracle离线满分不属于模型性能结果。

## 7. 开启包产物

```text
outputs/v11_cf04_e2_hybrid_semantic_dev_opening_v1_20260731/
├── task_source_snapshot.json
├── contracts_snapshot.json
├── base_policy_snapshot.json
├── hybrid_policy_snapshot.json
├── prompt_snapshot.json
├── output_schema_snapshot.json
├── run_config_snapshot.json
├── execution_authorization_request_snapshot.json
├── runner_snapshot.py
├── model_payload_audit.json
├── candidate_report.json
└── artifact_manifest.json
```

manifest内11项正式产物的SHA-256已全部复核一致。

## 8. 当前不能做什么

当前不能：

- 调用DeepSeek；
- 创建真实运行结果；
- 读取或开启40条独立验证集；
- 根据尚不存在的模型结果修改验证集；
- 将CF-04标记为`passed`；
- 将Core Frozen改为`true`。

## 9. 下一步

下一步需要两类明确授权：

1. 若要发布本地提交，需要明确授权将`ade5fa5`、`c307b3f`及本开启包后续提交推送至指定GitHub仓库；
2. 若要运行开发复核，需要明确授权将55条合成v2任务、5个契约视图和冻结语义提示词发送至DeepSeek，使用`deepseek-v4-flash`执行一次且不调用冶金工具。

GitHub发布授权和外部API执行授权相互独立，不能互相替代。
