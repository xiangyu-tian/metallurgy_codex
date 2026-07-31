# v1.1 CF-04 E2独立语义验证集v1候选

## 结论

E2任务v2已经通过可复现性、产物哈希和标签可观察性复审，并被锁定为后续验证构造的开发源。基于不同基础任务组、不同边界值和独立ID空间，已生成一份尚未交给模型的独立语义验证候选：

```text
dataset_id = E2-INDEPENDENT-SEMANTIC-VALIDATION-V1-CANDIDATE-20260731
task_count = 40
model_execution_count = 0
external_api_calls = 0
CF-04 = in_progress
Core Frozen = false
```

“锁定”只表示此后不得根据模型结果调整验证任务，不表示CF-04已经通过。

## 1. v2开发源复审

复审对象：

```text
E2-CONTRACT-BOUNDARY-PILOT-V2-CANDIDATE-20260731
```

| 检查 | 结果 |
|---|---:|
| manifest内产物哈希 | 通过 |
| 已保存任务与重新构建结果 | 完全一致 |
| 已保存变换事件与重新构建结果 | 完全一致 |
| 结构标签可观察性 | 0项错配 |
| 语义标签参考复核 | 0项错配 |

复审决定：

```text
accepted_as_locked_development_source_for_validation
```

该决定的适用范围仅为“开发源锁定”，不是`CF-04=passed`或`Core Frozen=true`。

## 2. 为什么不直接把v2再次当作验证集

v2的55条任务已经参与：

- v1/v1.1策略错误分析；
- 双层门控设计；
- 提示词和输出Schema开发；
- 标签可观察性修复。

继续在同一批表面输入上报告性能，会把开发反馈混入验证结果。因此，新候选使用：

1. 不同的`base_task_id`；
2. 不同的`base_task_group_id`；
3. 不同的任务与事件ID命名空间；
4. 不同的歧义候选、超域值和不支持系统；
5. 与v2不同的最终模型可见状态。

## 3. 候选设计

每个工具8条任务，共5个工具、40条任务：

| 条件 | 语义层标签类型 | 每工具数量 |
|---|---|---:|
| ready | 语义阴性 | 1 |
| ambiguous | 语义阴性、结构阳性 | 1 |
| unavailable | 语义阴性、结构阳性 | 1 |
| version mismatch | 语义阴性、结构阳性 | 1 |
| contract OOD | 语义阳性 | 1 |
| unsupported system | 语义阳性 | 1 |
| ambiguous + OOD | 语义阳性、结构阳性 | 1 |
| OOD + unavailable | 语义阳性、结构阳性 | 1 |

汇总：

| 项目 | 数量 |
|---|---:|
| 任务 | 40 |
| 变换事件 | 45 |
| 语义阳性 | 20 |
| 语义阴性 | 20 |
| 多标签任务 | 10 |
| call | 5 |
| clarify | 10 |
| refuse | 25 |

该平衡针对LLM语义层的阳性/阴性识别，不追求三个最终动作等比例。

## 4. 防泄漏与独立性审计

自动审计全部通过：

| 检查 | 结果 |
|---|---:|
| 任务ID唯一且与开发集隔离 | 通过 |
| 事件ID唯一且与开发集隔离 | 通过 |
| 基础任务ID与开发集隔离 | 通过 |
| 基础任务组与开发集隔离 | 通过 |
| 40个最终可见状态内部唯一 | 通过 |
| 与55条v2最终可见状态重合 | 0 |
| 五个工具的边界变换值均不同于开发集 | 通过 |
| 结构与语义标签可由最终输入复算 | 0项错配 |
| 最终动作可由冻结政策复算 | 0项错配 |

独立性边界需要准确表述：

> 这是同一批5个工具和同一组契约下的“未见基础任务与未见边界值”验证，不是对未见工具家族的外推验证。

## 5. 金标签来源

验证集不依赖逐题专家判断：

```text
最终structured_state
+ versioned tool contract
→ 确定性结构检查
+ 独立契约参考验证器
→ 结构flags与语义flags
→ 冻结动作政策
→ call / clarify / refuse
```

变换历史只用于审计，不能作为模型面对的标签证据。

## 6. 执行封存状态

当前候选明确记录：

```text
external_api_execution_authorized = false
model_execution_count = 0
model_executed = false
model_performance_claim_allowed = false
confirmatory_inference_allowed = false
```

因此，本轮没有模型结果，也没有模型性能结论。

## 7. 产物

```text
outputs/v11_cf04_e2_independent_validation_v1_candidate_20260731/
├── validation_split_snapshot.json
├── e2_validation_tasks_v1.json
├── mutation_events_validation_v1.json
├── v2_source_review_record.json
├── independence_audit.json
└── artifact_manifest.json
```

## 8. 测试

| 测试范围 | 结果 |
|---|---:|
| 独立验证候选专项测试 | 8 passed |
| Core Freeze完整回归 | 153 passed |

所有测试均为本地执行，外部API调用为0。

## 9. 后续实验顺序

验证候选一旦提交后，不再根据模型结果修改。合理顺序为：

1. 在v2开发集上完成语义层提示词开发复核；
2. 冻结模型、提示词、Schema、温度和重试参数；
3. 建立单独的验证执行授权；
4. 在40条独立候选上同时运行：
   - LLM-only flags基线；
   - 确定性结构检查＋LLM语义检查双层门控；
5. 比较语义Macro-F1、多标签完全匹配率、最终动作准确率和提前调用率；
6. 在不改验证集的前提下报告全部成功、失败与解析异常；
7. 再决定是否扩展重复次数和样本量。
