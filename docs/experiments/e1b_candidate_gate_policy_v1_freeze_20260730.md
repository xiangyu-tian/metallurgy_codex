# E1b候选门控策略v1冻结记录

- 策略ID：`E1B-CANDIDATE-GATE-POLICY-V1`
- 策略版本：`1.0.0`
- 状态：`candidate_frozen_pre_gate`
- 策略SHA-256：`4d34ddc0a8d53d46f0aabf1469469dab243b9ddb6c03a5e8e849b9763801c1d5`
- 适用范围：A001、A002、A003、A004、B019的ready、契约内、已验证计算任务
- 当前结论性质：开发集拟合，不是确认性证据，不代表Core Frozen

## 1. 冻结目的

E1b v2已经完成45题、两个条件、三次重复，共270个真实API单元的收益估计。为遵守防循环评价要求，必须在观察独立`gate_evaluation`效果前，将收益结论转化为不可事后调整的机器策略。

本次冻结把以下两件事分开：

1. `candidate_gate_policy_v1.json`只包含可观察特征、规则、动作和固定阈值；
2. 开发集收益及拟合数字只进入`development_fit_report.json`，不参与运行时匹配。

## 2. 动作语义

策略输出两个互斥动作：

```text
CALL_VERIFIED_TOOL
ANSWER_WITHOUT_TOOL
```

`CALL_VERIFIED_TOOL`表示该题应使用已验证工具获得计算证据；`ANSWER_WITHOUT_TOOL`表示该题在当前证据下不应调用工具。它不是“可随意自主调用”，而是与E1b的`No Tool`条件对应。

该策略只处理“调用是否有收益”。输入缺失、契约越界、服务不可用和高风险人工复核仍由E2边界门控处理，不能由本策略覆盖。

## 3. 冻结规则

### 规则一：严格版本化数值

当：

```text
precision_policy = strict_versioned
```

输出：

```text
CALL_VERIFIED_TOOL
```

理由是答案受冻结常数版本和窄容差约束。开发运行表明，模型常会使用记忆中的常用原子量，而不是题目要求的冻结原子量。

### 规则二：高动态范围且需要重标度的组分归一化

当：

```text
source_tool_id = A004
composition_dynamic_range >= 100
composition_requires_rescaling = true
```

输出：

```text
CALL_VERIFIED_TOOL
```

动态范围定义为非零组分绝对值最大值除以最小值；需要重标度定义为组分和与1的差大于`1e-12`。阈值100在独立Gate运行前固定，不允许在看到Gate结果后优化。

### 默认规则

其余任务输出：

```text
ANSWER_WITHOUT_TOOL
```

这包括当前已验证的普通单位换算、中性化学式元素计数、教学近似精度摩尔质量、简单杠杆定律，以及不满足上述数值条件的组分归一化。

## 4. 防止题目记忆和公式过拟合

策略明确禁止使用：

- `task_id`；
- `base_task_group_id`；
- `problem_text`；
- 具体化学式；
- 期望答案；
- Gate评测结果。

自动测试会替换题号、题组、题面和化学式，并验证决策保持不变。规则使用的是精度契约和数值条件，而不是“Fe2O3调用、其他式子不调用”一类题目白名单。

## 5. 开发集回顾性拟合

在45题、135个配对重复单元上：

| 策略 | 正确率 | 调用单元 |
| --- | ---: | ---: |
| 始终不调用 | 86.67% | 0/135 |
| 始终调用 | 100.00% | 135/135 |
| 候选策略v1 | 99.26% | 21/135 |

候选策略相对始终不调用提高12.59个百分点；相对始终调用少114次调用，仅损失1个正确单元。开发集中共有18个正收益单元，策略捕获17个，即94.44%。

这些数字只说明策略能够压缩开发集中的无收益调用，同时保留大部分已观察收益。它们不证明策略具有泛化能力，也不能作为确认性置信区间或最终论文结论。

## 6. 未纳入规则的开发异常

B019百分比条件出现一次JSON格式错误，但数值本身正确。由于该异常更像输出格式波动而不是科学计算错误，v1没有据此强制调用B019。

A003严格版本条件中的Fe2O3在三次No Tool运行中均正确，但v1仍按精度契约调用。这样做保留了规则的可迁移性，避免形成化学式例外表。

## 7. 冻结产物

主要文件：

- `Tools/core_freeze/e1b_v2/candidate_gate_policy_v1.json`
- `Tools/core_freeze/e1b_v2/apply_candidate_gate_policy.py`
- `outputs/e1b_v2_candidate_gate_policy_v1_20260730/development_policy_assignments.csv`
- `outputs/e1b_v2_candidate_gate_policy_v1_20260730/development_fit_report.json`
- `outputs/e1b_v2_candidate_gate_policy_v1_20260730/artifact_manifest.json`

Manifest同时绑定策略、执行器快照、动作审计以及三项开发输入的SHA-256。

## 8. 下一步

下一阶段可以解封27题`gate_evaluation`快照。执行时必须满足：

1. 使用当前策略SHA-256；
2. 不修改v1规则、优先级或阈值；
3. 先生成27题的策略动作清单，再运行模型条件；
4. Gate结果只用于评价v1，不用于回写v1；
5. 如需提出v2，必须在完整报告v1的后置结果之后另行登记；
6. Gate评测仍是开发性独立验证，不自动使E1b或Core Freeze通过。
