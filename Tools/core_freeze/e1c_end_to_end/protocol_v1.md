# E1c端到端损失分解协议v1

- 协议ID：`E1C-END-TO-END-PROTOCOL-V1`
- 状态：`candidate_frozen_pre_run`
- 日期：2026-07-31
- 上游策略：`E1B-CANDIDATE-GATE-POLICY-V1`
- 上游策略SHA-256：`4d34ddc0a8d53d46f0aabf1469469dab243b9ddb6c03a5e8e849b9763801c1d5`
- 推断性质：开发性机制实验，不是Core Freeze确认性实验

## 1. 研究目标

E1b证明验证工具在部分任务上存在可重复收益，并形成了候选调用边界。E1c不再回答“工具本身有没有用”，而是分解端到端系统的损失：

```text
端到端损失
= 边界决策损失
+ 工具选择损失
+ 参数生成损失
+ 工具执行损失
+ 结果表达损失
```

## 2. 冻结策略动作

机器策略只输出：

```text
CALL_VERIFIED_TOOL
ANSWER_WITHOUT_TOOL
```

该动作由E1b策略v1在API运行前派生，不由人工逐题标注，也不允许根据E1c结果回写策略v1。

## 3. 实验条件

### C0：No Tool

模型无工具，直接回答。提供无工具准确率基线。

### C1：Forced Verified Tool + Oracle Parameters

始终使用目标验证工具和预注册参数。提供工具可用性与结果表达上限。

### C2：Model Gate + Oracle Downstream

模型只判断`CALL_VERIFIED_TOOL`或`ANSWER_WITHOUT_TOOL`。若调用，系统使用预注册目标工具和Oracle参数；若不调用，模型直接回答。

主要测量：

- 边界动作正确率；
- 过度调用率；
- 漏调用率；
- 在Oracle下游条件下的最终正确率。

### C3：Oracle Gate + Model Parameters

机器策略决定是否调用。需要调用时，模型已知目标工具，只生成参数；系统执行工具并让模型基于结果作答。不调用时直接回答。

主要测量：

- 参数结构有效率；
- 参数完全正确率；
- 工具执行成功率；
- 最终正确率。

### C4：Direct FC

向模型提供相同的5个工具Schema和普通函数调用说明，不提供候选边界规则。模型自主决定是否调用、选择工具并生成参数。

### C5：Boundary-Guided FC

向模型提供与C4完全相同的5个工具Schema，并增加冻结边界规则。模型自主决定是否调用、选择工具并生成参数。

C4与C5的差异只能是边界规则提示，不得改变Schema、工具顺序、温度、模型或任务。

## 4. 主要比较

| 比较 | 解释 |
| --- | --- |
| C2 vs 冻结策略动作 | 模型能否识别调用边界 |
| C3 vs C1的策略选中路径 | 参数生成损失 |
| C4 vs C5 | 边界指导是否改善自主函数调用 |
| C5 vs C3 | 工具选择与自主边界的附加损失 |
| C5 vs C1 | 完全端到端相对工具上限的总损失 |

## 5. 错误归因优先级

每个运行单元只分配一个首要失败阶段：

```text
provider_failure
→ decision_parse_failure
→ boundary_decision_error
→ tool_selection_error
→ parameter_parse_failure
→ parameter_value_error
→ tool_execution_error
→ answer_parse_failure
→ final_answer_error
→ success
```

后续错误仍记录为附加标志，但不能覆盖更早阶段。

## 6. 数据隔离

新任务不得复用E1b的`base_task_group_id`。数据分为：

- `runner_development`：24题，用于API连通性、解析和工程调试；
- `end_to_end_evaluation`：36题，在提示词、运行器和评分器冻结前禁止API运行。

开发结果只能修复通用实现错误。若修改提示词、动作定义、错误归因或评分规则，必须生成新版本并重新冻结，之后才能打开后置集。

## 7. 任务构成

| 工具 | 开发题 | 后置题 | 作用 |
| --- | ---: | ---: | --- |
| A001 | 4 | 6 | 无收益调用控制 |
| A002 | 4 | 6 | 结构化参数与输出 |
| A003 | 8 | 12 | 严格/近似最小差异边界 |
| A004 | 4 | 8 | 高动态范围规则及对照 |
| B019 | 4 | 4 | 冶金计算与多参数生成 |
| 合计 | 24 | 36 | |

后置集预计包含10个调用任务和26个不调用任务。A003严格/近似变体按同一基础题组进入同一数据分区。

## 8. 指标

边界指标：

- Action Accuracy；
- CALL类Precision、Recall、F1；
- Over-call Rate；
- Bypass Rate。

路由与参数指标：

- Tool Selection Accuracy；
- Parameter JSON Validity；
- Exact Parameter Match；
- Tool Execution Success。

端到端指标：

- Final Answer Accuracy；
- Stage-attributed Error Rate；
- Tool Call Rate；
- Token、延迟、重试次数。

## 9. 解释边界

E1c只在5个`verified_core`工具和可执行真值任务上研究端到端损失。它不证明：

- 120工具规模路由已经解决；
- 神经网络模型的预测可靠性；
- 开放式工程建议的科学正确性；
- Core Freeze已经完成。

只有完成E1c后，才进入更大工具池下的E3路由与相似工具干扰实验。
