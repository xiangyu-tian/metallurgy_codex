# Core Frozen 证据检查清单 v1.1

## 文档状态

- 版本：`1.1-rc1`
- 日期：2026-07-31
- 适用协议：`research_protocol_v1.1-rc1`
- 配套数据规范：`dataset_executable_reference_policy_v1.0-rc1`
- 当前阶段：可执行真值主线验证
- Core Frozen：`false`

本清单替代 `core_freeze_checklist_v1.0.md` 对当前 v1.1 主线的治理作用。v1.0 清单继续作为历史记录保留，但其中依赖专家逐题金标准的 CF-01、CF-02、CF-03 和 CF-05 不能用于决定 v1.1 是否冻结。

## 1. 编号迁移原则

v1.1 的 CF 编号重新绑定到可执行真值冻结门槛：

- 不把 AI-A、AI-B 共识或单人裁决升级为确认性金标准；
- 不要求专家逐题自由判断作为正式实验启动条件；
- 不把 120 个 Schema-only 工具称为 120 个已验证计算引擎；
- 正式真值只来自 G1、G2 和 C1；
- 旧 Track A 银标保留作探索和错误发现；
- 旧 Track B 模板保留作自然任务种子，不直接提供正式可接受工具集合。

旧、新编号语义不同，不得把旧清单状态直接复制到本清单。

## 2. 状态定义

- `pending`：尚未开始；
- `in_progress`：已有证据，但未达到全部验收门槛；
- `passed`：机器可复核证据完整并达到门槛；
- `failed`：已执行但未达到门槛；
- `waived`：有书面理由、影响分析和项目审批的正式豁免。

## 3. v1.1 Core Freeze总门槛

| ID | 冻结证据 | 最低验收标准 | 当前状态 | 当前证据与缺口 |
|---|---|---|---|---|
| CF-01 | 协议与数据规范兼容性 | v1.1研究问题、G1/G2/C1真值、S1限制、数据生产和`core_frozen=false`一致 | `passed` | `outputs/v11_cf01_cf02_audit_20260731/`；8项兼容性检查全部通过 |
| CF-02 | `verified_core`工具及独立参考 | 至少3个工具；契约字段、来源、适用域、限制、哈希、正常/边界案例和独立参考均通过 | `passed` | A001、A002、A003、A004、B019共5工具；27/27参考案例通过；11项审计检查通过 |
| CF-03 | E1b基础任务与收益先导 | 基础任务、独立参考、No Tool/Forced Tool对照、重复和防循环划分可复现 | `in_progress` | 候选证据审计已通过：45条收益任务和27条门控任务完成3次成对重复，任务/任务对/基础任务组零交叉；待CF-08/CF-09冻结正式重复次数和样本量 |
| CF-04 | E2契约边界变换 | 缺参、歧义、契约超域、不支持、不可用和版本错配可由规则复算；多标签与动作优先级测试通过 | `pending` | 尚未形成v1.1正式变换集 |
| CF-05 | E3参数、可接受工具与契约近邻 | 参数规范化、单一/等价可接受工具、0/4/8契约近邻和嵌套池测试通过 | `in_progress` | 五工具端到端选择已验证；17/50/100/120契约目录与近邻生成仍未完成 |
| CF-06 | 17/50/100/120 Schema API可行性 | 实测函数数量、Token、上下文、延迟、错误、`tool_choice=none`和供应商限制 | `pending` | 尚未按v1.1 Schema-only目录口径执行 |
| CF-07 | 数据层级与泄漏审计 | `controlled_confirmatory`、`naturalistic_validation`、`exploratory_domain_cases`分层；家族划分和收益校准/评价隔离通过 | `in_progress` | E1b/E1c受控集已分区；自然验证层和探索层尚未冻结 |
| CF-08 | 先导波动与功效分析 | 估计任务家族、工具家族、重复波动和主要效应；固定正式重复次数 | `in_progress` | E1b/E1c已有单次或小重复结果；尚无正式功效分析 |
| CF-09 | 样本量附录 | 生成并审批v1.1样本量和重复次数附录 | `pending` | 待CF-08 |
| CF-10 | 新统计接口与报告模板干跑 | v1.1 E1/E2/E3字段通过输入校验、聚合、Bootstrap/GLMM和报告模板干跑 | `in_progress` | 旧CF-11基础设施已完成；尚未使用v1.1真实候选数据干跑 |
| CF-11 | 正式资产哈希冻结 | 工具、契约、生成器、任务、参考结果、评分器、配置和报告模板全部进入不可变manifest | `in_progress` | verified_core、E1b、E1c已有局部manifest；全项目冻结清单尚未形成 |
| CF-12 | 最终审查与冻结决定 | CF-01至CF-11全部`passed`或正式`waived`；限制声明、偏离记录和项目审批完整 | `pending` | `core_frozen=false` |

只有 CF-01 至 CF-11 全部为 `passed` 或具有正式 `waived`，且 CF-12 完成最终审查后，才能把 v1.1 状态改为：

```text
core_frozen = true
```

## 4. CF-01验收记录

```yaml
check_id: CF-01
title: v1.1协议与可执行数据规范兼容性
status: passed
audit_id: V11-CF01-CF02-AUDIT-20260731
evidence:
  - outputs/v11_cf01_cf02_audit_20260731/audit_report.json
  - outputs/v11_cf01_cf02_audit_20260731/artifact_manifest.json
  - Tools/core_freeze/audit_v11_cf01_cf02.py
acceptance_result:
  compatibility_checks: 8/8
  formal_truth_tiers: [G1, G2, C1]
  provisional_silver_promoted: false
  legacy_track_a_gold_reused: false
scope:
  - 仅证明协议、数据规范和真值治理一致
  - 不代表后续实验或Core Frozen通过
```

冻结源文件：

| 文件 | SHA-256 |
|---|---|
| `research_protocol_v1.1-rc1.md` | `14e219ddd9b9891f338845376d46f9442794b474421bda9d18fa1e8796712d25` |
| `dataset_executable_reference_policy_v1.0-rc1.md` | `4984dc17e65bda9d0250b8e8c199573bfc2abdee70091258c858d0be9ca01d8d` |
| `research_protocol_revision_rationale_20260730.md` | `264e6acf9a382982dc6b42a7d8e6d6cb47c652f82aecda5a65b2fbf19dbc900c` |

## 5. CF-02验收记录

```yaml
check_id: CF-02
title: 至少3个verified_core工具及独立参考验证
status: passed
audit_id: V11-CF01-CF02-AUDIT-20260731
verified_tools: [A001, A002, A003, A004, B019]
verified_tool_count: 5
reference_case_count: 27
passed_reference_case_count: 27
failed_reference_case_count: 0
normal_boundary_coverage: passed
published_manifest_verified: true
core_frozen: false
scope:
  - 只接受五个工具各自verification_scope内的结论
  - 不覆盖其余12个已实现工具
  - 不覆盖103个规划工具
  - 不证明120工具均可执行
```

冻结源文件：

| 文件 | SHA-256 |
|---|---|
| `tool_contract.schema.json` | `349ac1033c8d2e03a297ef3e88ccacf7ad05e5d8f66fc1bd2ae73df90afcd3ca` |
| `contracts_v1.json` | `9df57db7836dbcb24d5b5d7f5b487003ade3a33955d01e2a827633aaa14fc0ec` |
| `reference_cases_v1.json` | `8efabe718a67e34d471921735461f654d5541559dbe5e322b7172d0250367d1f` |
| `validate_verified_core.py` | `6b0a342bb7a53876b849d76fca3bf1243a8436d2a58d70965a8cfe6cad16cd4c` |
| 已发布验证报告 | `9b50c51f79370316544ef0c226ea88e98c3c0eda76a03919afb1b77a0b657341` |
| 已发布manifest | `e61f0f909fda929c4fd5b59031c046009aa2c797e52ab102e97bf7d0e6fa7058` |

## 6. CF-03候选验收记录

```yaml
check_id: CF-03
title: E1b基础任务、收益先导与防循环划分
status: in_progress
audit_id: V11-CF03-CANDIDATE-AUDIT-20260731
candidate_evidence_status: passed
evidence:
  - outputs/v11_cf03_candidate_20260731/cf03_audit_report.json
  - outputs/v11_cf03_candidate_20260731/benefit_evidence_registry.json
  - outputs/v11_cf03_candidate_20260731/power_input.json
  - outputs/v11_cf03_candidate_20260731/artifact_manifest.json
  - Tools/core_freeze/audit_v11_cf03.py
acceptance_result:
  verified_tools: [A001, A002, A003, A004, B019]
  benefit_tasks: 45
  benefit_base_task_groups: 26
  benefit_paired_repeats: 135
  gate_tasks: 27
  gate_base_task_groups: 16
  gate_paired_repeats: 81
  pilot_model_run_repeats: 3
  task_id_overlap: 0
  task_pair_id_overlap: 0
  base_task_group_id_overlap: 0
  pilot_results_promoted_to_confirmatory: false
  tool_benefit_written_back_to_base_truth: false
pending:
  - CF-08功效分析审批
  - 正式模型重复次数冻结
  - CF-09样本量附录审批
core_frozen: false
```

本次通过的是“CF-03候选证据可复现性”，不是CF-03最终冻结。E1b收益校准集用于估计先导效应，独立门控集用于检验冻结策略；E1c只登记为机制层次的次要证据，不与E1b主要收益效应合并。

## 7. 旧CF-01/CF-02资产的保留方式

### AI辅助Track A

`track_a_provisional_silver.json`继续保留：

```text
label_tier = provisional_silver
formal_cf01_eligible = false
formal_cf03_eligible = false
```

用途仅限：

- 发现标签体系歧义；
- 提供自然表达种子；
- 记录未来需要领域复核的案例；
- 作为探索性对照。

### Track B模板

旧20任务模板继续保留为自然任务和路由错误分析种子。未经契约自动匹配和等价验证，不得将其中人工填写的：

- `acceptable_tools`；
- `unacceptable_near_neighbors`；
- `similarity_ratings`；

称为v1.1确认性金标准。

## 8. 下一执行点

CF-01和CF-02通过后，已完成CF-03候选证据整理。下一执行点转入CF-08，并用CF-03的`power_input.json`完成正式重复次数和样本量论证：

1. 固定E1b主要效应、聚类单位和最小有意义效应；
2. 使用基础任务组聚类，而不是把135个重复对视为独立样本；
3. 评估任务家族、工具家族和重复运行的波动；
4. 提出正式任务数与模型重复次数候选方案；
5. 审批`sample_size_addendum_v1.1`后再决定CF-03、CF-08和CF-09是否通过。
