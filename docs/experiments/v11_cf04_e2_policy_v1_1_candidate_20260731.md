# v1.1 CF-04 E2 flags-only策略候选

## 结论

E2模型策略v1.1候选已经完成本地实现、离线测试和首轮响应反事实回放：

```text
candidate_status = prepared_not_authorized
independent_model_recheck = pending
CF-04 = in_progress
Core Frozen = false
```

v1.1不再要求模型重复输出可由规则计算的`primary_status`和`action`。模型只输出全部底层边界事实flags，系统按冻结的`e2-readiness-policy-v1.0.0`确定性派生状态和动作。

这不是降低评分标准，而是明确系统职责：

```text
大模型
→ 识别全部边界事实flags

冻结政策
→ 按优先级派生primary_status
→ 派生call / clarify / refuse
```

研究仍然测量模型是否正确识别缺参、歧义、超域、不支持、不可用和版本错配；最终动作错误仍会被统计，但不再把一个可计算字段的格式错误重复计算为模型事实识别错误。

## 1. 为什么需要v1.1

首轮v1开发先导中：

| 指标 | 结果 |
|---|---:|
| API完成 | 55/55 |
| 可解析JSON | 55/55 |
| flags字段合法 | 55/55 |
| action字段合法 | 55/55 |
| 聚合primary status合法 | 13/55 |
| 严格Schema有效率 | 23.64% |
| 独立字段flags完全匹配率 | 76.36% |
| 独立字段action准确率 | 89.09% |

42条响应使用底层flag名称作为`primary_status`。例如：

```json
{
  "flags": ["missing_parameter"],
  "primary_status": "missing_parameter",
  "action": "clarify"
}
```

其中事实和动作均正确，但聚合状态违反Schema。v1.1删除这个重复输出责任，避免协议格式问题掩盖真正的边界分类能力。

## 2. 模型输出契约

v1.1唯一允许的输出结构：

```json
{
  "flags": [
    "missing_parameter",
    "unavailable"
  ]
}
```

Schema要求：

1. 根对象只能包含`flags`；
2. `flags`必须是数组；
3. 不允许重复值；
4. 不允许未知flag；
5. 不允许模型输出`primary_status`；
6. 不允许模型输出`action`；
7. 没有边界问题时输出空数组。

因此，v1.1真实运行中出现旧三字段格式仍会被严格判为无效，不会静默容错。

## 3. 确定性政策派生

沿用原冻结规则，不修改科学真值和动作优先级：

```text
missing_parameter / ambiguous_parameter
→ missing_or_ambiguous_input
→ clarify

contract OOD / unsupported system / model-card OOD / version mismatch
→ contract_out_of_domain_or_unsupported
→ refuse

unavailable
→ unavailable
→ refuse

无flags
→ ready
→ call
```

多标签全部保留。优先级只用于派生状态和动作，不能用于删除低优先级事实。

例如：

```json
{
  "flags": [
    "missing_parameter",
    "unavailable"
  ]
}
```

确定性派生：

```json
{
  "primary_status": "missing_or_ambiguous_input",
  "action": "clarify"
}
```

## 4. unsupported system与一般超域

v1提示词中模型经常把：

```text
contract_defined_unsupported_system
```

判断成：

```text
contract_defined_out_of_domain
```

两者通常都派生`refuse`，但错误原因不同。v1.1明确：

- `contract_defined_out_of_domain`：请求仍属于该工具声明的系统类型，但参数值、语法、元素集、组成范围或`verification_scope`超出边界；
- `contract_defined_unsupported_system`：请求的系统类型、相数、组元数或`requested_system`不在契约支持范围。

自动测试保证这两个flag不能互相替代。即使最终动作相同，细粒度flags错误仍按错误计入。

## 5. 首轮响应反事实回放

为验证“删除重复输出字段”这一协议变化，构建器从v1的55条已解析响应中显式投影：

```text
旧响应对象
→ 只提取flags字段
→ 使用v1.1严格flags Schema
→ 使用冻结政策派生状态和动作
```

结果：

| 指标 | 反事实回放 |
|---|---:|
| 新API调用 | 0 |
| Schema有效率 | 100.00% |
| flags完全匹配率 | 76.36%（42/55） |
| flags平均Jaccard | 83.64% |
| flags Macro-F1 | 79.93% |
| 派生primary status准确率 | 89.09% |
| 派生action准确率 | 90.91% |
| Invalid Execution Rate | 0.00% |
| Premature Call Rate | 0.00% |
| OOD Call Rate | 0.00% |

该回放只说明：如果把同一批v1事实预测交给v1.1后处理器，42条聚合状态格式错误将不再污染严格Schema评分。

它不能证明新提示词改善了：

- unsupported system识别；
- 多标签完整保留；
- 模型重复稳定性；
- 新任务泛化。

因为回放没有重新调用模型。

## 6. 估计对象

v1.1模型层主要估计对象固定为：

```text
全部底层flags的完全匹配率
支持类别Macro-F1
多标签Jaccard
各flag Precision / Recall / F1
```

系统层派生指标包括：

```text
primary status准确率
action准确率
Invalid Execution Rate
Premature Call Rate
OOD Call Rate
```

这样论文可以分别回答：

1. 模型是否识别了正确且完整的边界事实；
2. 确定性政策是否把这些事实转换成正确动作。

## 7. 防泄漏和执行门槛

提示词仍不暴露：

- `mutation_types`；
- `expected_flags`；
- 任务ID；
- 评分答案。

运行器还要求单独存在并通过哈希校验的：

```text
execution_authorization_development_v1_1.json
```

当前该文件不存在，授权请求状态为：

```text
awaiting_explicit_user_authorization
```

因此，候选包不能自行访问DeepSeek API。

## 8. 研究边界

v1.1是在同一55条开发任务上根据v1错误结构形成的新策略，因此：

1. 下一次同任务API运行只能称为开发复核；
2. 不能把性能提升表述为无偏泛化效果；
3. 正式E2实验必须在策略冻结后使用独立任务或独立变体；
4. 单次开发复核不能替代重复波动估计和样本量分析；
5. CF-04、CF-08 E2组件和CF-09 E2组件继续保持未通过。

## 9. 候选产物

```text
outputs/v11_cf04_e2_policy_v1_1_candidate_20260731/
├── prompt_candidate.json
├── output_schema_candidate.json
├── run_config_candidate.json
├── execution_authorization_request.json
├── runner_candidate.py
├── counterfactual_replay_records.jsonl
├── counterfactual_replay_report.json
├── candidate_report.json
└── artifact_manifest.json
```

候选manifest绑定：

- 55任务源；
- verified_core契约；
- 冻结E2政策；
- v1成功运行manifest；
- v1诊断manifest；
- v1.1候选构建器。

## 10. 自动测试

v1.1新增8项专项测试，覆盖：

1. flags-only Schema和冻结哈希；
2. 禁止提示词泄露预期标签；
3. 禁止模型输出派生字段；
4. 多标签完整保留和确定性优先级；
5. unsupported system与一般超域不可互换；
6. 55任务离线完美输出；
7. 缺少执行授权时拒绝联网运行；
8. 反事实回放、manifest及防覆盖。

测试结果：

```text
E2相关定向测试：20 passed
Core Freeze完整回归：134 passed
```

## 11. 下一步

候选包通过回归后，应先提交并远程备份，再由用户明确授权：

1. 将55条合成E2任务；
2. 对应工具契约视图；
3. v1.1 flags-only冻结提示词；

发送到DeepSeek API执行一次开发复核。

API复核完成后，比较重点不是只看总准确率，而是检查：

- Schema有效率是否稳定达到100%；
- unsupported-system Recall是否高于v1回放的16.67%；
- 多标签完全匹配率是否提高；
- `clarify`动作准确率是否高于v1回放的79.17%。
