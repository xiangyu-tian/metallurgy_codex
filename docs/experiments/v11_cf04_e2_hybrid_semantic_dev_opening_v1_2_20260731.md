# v1.1 CF-04 E2双层门控语义层开发开启包v1.2

## 结论

v1.2是v1.1开发门失败后的最小修订候选，当前状态为：

```yaml
candidate_id: E2-HYBRID-SEMANTIC-DEV-OPENING-V1.2-20260731
status: prepared_not_authorized
task_count: 55
external_api_calls: 0
external_api_execution_authorized: false
validation_dataset_access: forbidden
confirmatory_inference_allowed: false
core_frozen: false
```

该开启包不授权新的DeepSeek调用，也不允许读取或执行40条独立验证候选。

## 1. 修订依据

v1.1运行完整，但晋级门仅通过8/11项：

- 语义标志宏F1为0.8295，低于0.90；
- 合并标志精确数为45/55，低于52/55；
- 不支持系统召回率为0.8333，低于0.90。

10条语义误差集中为三个映射问题：

1. 把缺失或显式歧义参数升级成语义OOD；
2. 把多个组成标量误读为多个热力学组元；
3. 把显式相数不匹配归为OOD，而不是不支持系统。

## 2. 唯一实质修订

v1.2提示词新增三条证据规则：

- 缺失或显式歧义字段只由结构层处理，不能单独作为语义越界证据；
- 不得从参数字段数量或组成标量数量推断组元数或相数；
- 显式系统、相数或组元数不匹配归类为`contract_defined_unsupported_system`。

以下内容保持不变：

- 55条v2合成开发任务；
- 5个版本化工具契约；
- 双层门控和确定性结构检查器；
- 语义输出Schema；
- 11项冻结晋级门及全部阈值；
- 模型、端点、温度、单次重复和工具禁用策略；
- 40条独立验证集的密封状态。

## 3. 载荷和隔离审计

开启包生成时已确认：

```yaml
payload_audit_status: passed
payload_count: 55
leakage_error_count: 0
gold_labels_sent: false
mutation_history_sent: false
validation_dataset_sent: false
external_api_calls: 0
```

## 4. 版本绑定

| 文件 | SHA-256 |
|---|---|
| `prompts_hybrid_semantic_v1_2.json` | `4e0f8a258d8472aead43d5c7b0b617226ebe5e8bff44dbcd7c5e254f8223a52d` |
| `run_config_hybrid_semantic_development_v1_2.json` | `89d57cfe5d54246d989408de77b43c00c4dbd2e9b7239d81d6b9d148e5bea39e` |
| `run_e2_hybrid_semantic_development.py` | `c8c0254fe803e69dfd503465b35c00cebb8a51935f6590114fa58454c62d3ac8` |
| `execution_authorization_request_hybrid_semantic_v1_2.json` | `a815ab29dce6be6d173fa8911448ffede7630ca47f6540d3a9dd247f20e051c5` |
| 开启包`artifact_manifest.json` | `dc12c1ce242ad504341a8dc4cc11e55d7325ca9bc31fa19f27ea4db69498e621` |

开启包路径：

`outputs/v11_cf04_e2_hybrid_semantic_dev_opening_v1_2_20260731`

## 5. 允许的下一步

在获得新的、明确绑定v1.2的外部执行授权前，只允许：

- 代码和manifest复核；
- 离线测试；
- 文档审查；
- Git本地提交。

不允许：

- 第二次DeepSeek调用；
- 使用v1.1授权执行v1.2；
- 打开40条独立验证候选；
- 调用冶金工具；
- 将开发结果表述为确认性性能结论。

## 6. 后续执行状态

v1.2随后获得独立授权并完成一次55条开发复核：

```yaml
run_id: E2-HYBRID-SEMANTIC-DEV-023291404A0C453D
completed_count: 55
provider_failure_count: 0
gate_checks_passed: 8
gate_checks_required: 11
decision: revise_on_development_only
validation_dataset_access_count: 0
```

因此，本文件保留为v1.2执行前冻结记录。v1.2没有开启40条验证集；后续仅形成开发集内v1.3候选。
