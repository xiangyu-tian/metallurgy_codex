# v1.1 CF-04 E2双层门控语义层开发开启包v1.1

## 结论

在任何外部执行之前，开发复核开启包已由v1升级为v1.1。唯一实质变化是将晋级标准从讨论结论固化为版本化规则、授权哈希绑定和可执行分析器：

```text
candidate_id = E2-HYBRID-SEMANTIC-DEV-OPENING-V1.1-20260731
status = prepared_not_authorized
external_api_calls = 0
validation_dataset_access = forbidden
```

v1开启包保持原样，状态改为：

```text
superseded_before_execution
```

没有发生v1外部运行，也没有覆盖其产物。

## 1. 为什么需要v1.1

如果先运行模型、再决定什么结果算“足够好”，会产生事后选择空间。v1.1要求在执行前固定：

- 完整性标准；
- Schema标准；
- 结构检查标准；
- 语义Macro-F1；
- 合并flags准确性；
- 最终动作准确性；
- 两类语义标签召回率；
- 提前调用上限；
- 验证集封存状态。

## 2. 冻结晋级标准

| 检查 | 晋级条件 |
|---|---:|
| 完成任务 | 55/55 |
| 供应商失败 | 0 |
| 语义Schema有效 | 55/55 |
| 确定性结构flags正确 | 55/55 |
| 语义标签Macro-F1 | ≥ 0.90 |
| 合并flags完全匹配 | ≥ 52/55 |
| 最终动作正确 | ≥ 53/55 |
| contract OOD召回率 | ≥ 0.90 |
| unsupported system召回率 | ≥ 0.90 |
| 非法任务提前调用 | ≤ 1 |
| 独立验证集访问次数 | 0 |

决策规则：

```text
11项全部通过
→ advance_to_validation_preparation

任一失败或指标缺失
→ revise_on_development_only
```

不存在“部分通过”。即使全部通过，也只允许准备新的验证开启包，不自动授权访问或执行独立验证集。

## 3. 标准来源

门槛参考了v1.1中51条可观察开发任务的诊断结果：

```text
flags exact = 48/51 = 94.12%
action correct = 49/51 = 96.08%
```

因此将新55条开发任务的离散门槛固定为：

```text
merged flags exact ≥ 52/55
action correct ≥ 53/55
```

旧诊断不是正式基线，门槛只用于开发候选是否具备进入独立验证准备阶段的工程判断。

## 4. 失败后的处理

若v1语义提示词未通过：

1. 不得读取或运行40条独立验证候选；
2. 完整保留失败运行及其逐条结果；
3. 不得覆盖当前提示词或结果；
4. 只能创建新的版本化开发候选；
5. 在重新进入验证准备前再次通过同一晋级门；
6. 最多允许再创建1个提示词修订候选，之后需要重新审查设计。

## 5. 授权绑定

未来开发执行授权除原有任务、提示词、Schema、配置和运行器哈希外，还必须绑定：

```text
advancement_gate_id
advancement_gate_sha256
```

运行结果同时保存晋级门快照。结果分析器也记录：

- 运行产物manifest哈希；
- 晋级门哈希；
- 混合政策哈希；
- 分析器哈希。

## 6. 开启包

```text
outputs/v11_cf04_e2_hybrid_semantic_dev_opening_v1_1_20260731/
├── task_source_snapshot.json
├── contracts_snapshot.json
├── base_policy_snapshot.json
├── hybrid_policy_snapshot.json
├── advancement_gate_snapshot.json
├── prompt_snapshot.json
├── output_schema_snapshot.json
├── run_config_snapshot.json
├── execution_authorization_request_snapshot.json
├── runner_snapshot.py
├── analyzer_snapshot.py
├── model_payload_audit.json
├── candidate_report.json
└── artifact_manifest.json
```

## 7. 测试状态

专项测试覆盖：

- 未授权拒绝；
- API载荷泄漏；
- 验证集隔离；
- Schema职责分离；
- 确定性结构层；
- Oracle离线功能链；
- 全通过晋级；
- 单项失败退回开发；
- 指标缺失失败关闭；
- 产物哈希；
- 防覆盖。

结果：

```text
11 passed
```

Core Freeze完整回归：

```text
164 passed
```

本结果只证明执行和治理链正确，不证明模型达到晋级标准。

## 8. 下一步

当前下一步仍是获得两项明确授权：

1. GitHub发布授权：发布本v1.1规则、分析器和开启包；
2. DeepSeek开发执行授权：发送55条v2开发任务、5个契约视图和冻结提示词，使用`deepseek-v4-flash`执行一次，不调用工具，不接触40条验证集。

两项授权相互独立。
