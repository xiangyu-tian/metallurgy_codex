# v1.1 CF-04 E2双层门控语义层开发开启包v1.3

## 结论

```yaml
candidate_id: E2-HYBRID-SEMANTIC-DEV-OPENING-V1.3-20260731
status: prepared_not_authorized
task_count: 55
external_api_calls: 0
external_api_execution_authorized: false
validation_dataset_access: forbidden
confirmatory_inference_allowed: false
core_frozen: false
```

v1.3是v1.2过度纠偏后的第二次开发修订。它不授权新的DeepSeek调用，也不允许读取40条独立验证候选。

## 1. 修订范围

唯一实质变化是提示词中的语义证据边界：

- 结构和语义flags独立累积；
- 全部越界的歧义候选仍产生语义flag；
- 服务不可用或版本错配不掩盖语义边界；
- unsupported只接受`request_context`中显式系统、相数或组元数不匹配；
- 参数值、单位、语法、元素集、组成范围和verification scope违反保持为OOD。

任务、契约、输出Schema、确定性结构检查、合并策略、动作策略和11项晋级门均未改变。

## 2. 隔离审计

```yaml
payload_audit_status: passed
payload_count: 55
leakage_error_count: 0
gold_labels_sent: false
mutation_history_sent: false
validation_dataset_sent: false
external_api_calls: 0
```

## 3. 版本绑定

| 文件 | SHA-256 |
|---|---|
| `prompts_hybrid_semantic_v1_3.json` | `9cc49fd63d8623c123173a711c642b4eaf4ea3769cf9d96eecd5b0d166dc866e` |
| `run_config_hybrid_semantic_development_v1_3.json` | `7ed97e1823e89fdd8e60c9e61faefe705e7a189b21832a4aa625184341ce282a` |
| `run_e2_hybrid_semantic_development.py` | `4ee1a2519ecf6060a8a6fc85d1f702e375fa5a6ba0d4118bb087b0114cd5aa70` |
| `execution_authorization_request_hybrid_semantic_v1_3.json` | `65a6678625aa068abd9c3ffdb3d7a9f21a733d6b746b744d3e060a9524c87318` |
| 开启包`artifact_manifest.json` | `ae5d83d17ca76edf6a1b98688ea1562e8701519c5c53238efbc631c07361d55c` |

开启包：

`outputs/v11_cf04_e2_hybrid_semantic_dev_opening_v1_3_20260731`

## 4. 当前允许与禁止事项

允许：

- 代码、提示词和manifest复核；
- 离线测试；
- 本地Git提交。

禁止：

- 使用v1.2授权执行v1.3；
- 再次调用DeepSeek；
- 打开40条独立验证候选；
- 调用冶金工具；
- 调整冻结晋级门；
- 形成确认性性能结论。
