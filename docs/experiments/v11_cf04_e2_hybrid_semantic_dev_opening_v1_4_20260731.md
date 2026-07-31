# v1.1 CF-04 E2双层门控语义层开发开启包v1.4

## 结论

```yaml
candidate_id: E2-HYBRID-SEMANTIC-DEV-OPENING-V1.4-20260731
status: prepared_not_authorized
task_count: 55
external_api_calls: 0
external_api_execution_authorized: false
validation_dataset_access: forbidden
confirmatory_inference_allowed: false
core_frozen: false
```

v1.4是双层门之间载荷契约的最小架构修订，不是新的提示词堆叠。

## 1. 机器可读确定性上下文

语义模型除原始`structured_state`外，会收到：

```yaml
deterministic_context:
  structural_flags: []
  missing_required_inputs: []
  ambiguous_parameter_paths: []
  explicit_domain_evidence:
    requested_system:
      status: supported | unsupported | not_provided
    requested_phase_count:
      status: matches_contract | mismatches_contract | not_provided | contract_unspecified
    requested_component_count:
      status: matches_contract | mismatches_contract | not_provided | contract_unspecified
  parameter_field_count_is_domain_count: false
```

这些字段由任务请求和版本化契约确定性计算，不包含语义金标。

## 2. 不变项

- 同一55条开发任务；
- 同一5份契约；
- 同一语义输出Schema；
- 同一DeepSeek模型和单次运行设置；
- 同一确定性合并和动作策略；
- 同一11项晋级门；
- 40条验证集继续密封。

## 3. 载荷审计

```yaml
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
| `prompts_hybrid_semantic_v1_4.json` | `b4e427dc1c9e396ae373811c56561b51cb3922de9b1dc6edea11acbc99b95abf` |
| `run_config_hybrid_semantic_development_v1_4.json` | `ce14af9264c053650f8e7a4c3c229023e1dfa3cc8f77fdc9021852c0c0b0ec04` |
| `run_e2_hybrid_semantic_development.py` | `e21181058c0e1c04109b7e81226e34b0752abba7fd62167f97912454f28f7fdb` |
| `execution_authorization_request_hybrid_semantic_v1_4.json` | `3f1db83a37f191535c60fab5ad541150953fe5c690fbf76c9de41003dede26c0` |
| 开启包`artifact_manifest.json` | `e2de0714f2c5da879a625b39ca4d3ad0cda8295983532135b267a0fea8a2efab` |

## 5. 当前限制

v1.4没有执行授权。允许离线测试、审查和本地提交；禁止：

- 新的DeepSeek调用；
- 使用v1.3授权执行v1.4；
- 访问40条验证集；
- 调用冶金工具；
- 修改冻结晋级门；
- 作确认性性能声明。
