# E1b v2 独立任务集

本目录生成并验证 E1b 的第二版开发任务集，用于比较：

```text
Forced Verified Tool（Oracle参数）
vs
No Tool
```

## 设计边界

- 参考答案由 `task_seeds_v2.json` 中的冻结事实和基础方程独立生成。
- 参考答案生成器不导入生产工具代码。
- 生产工具仅在验证阶段接收相同输入，并与独立参考答案比较。
- `benefit_estimation` 用于估计工具收益和形成后续门控规则。
- `gate_evaluation` 是按 `base_task_group_id` 隔离的后置评估集；在门控规则冻结前不得查看其模型效果。
- 数据状态保持 `prepared / development_candidate`，不宣称正式金标准或 Core Frozen。

## 规模

| 工具 | 任务数 |
| --- | ---: |
| A001 | 16 |
| A002 | 12 |
| A003 | 20 |
| A004 | 12 |
| B019 | 12 |
| 合计 | 72 |

其中 `benefit_estimation=45`，`gate_evaluation=27`。A003 的每个基础问题同时生成严格版本和近似版本，且两者始终位于同一数据分区。

## 执行

```powershell
& '.\.venv\Scripts\python.exe' 'Tools\core_freeze\e1b_v2\generate_e1b_v2.py'
& '.\.venv\Scripts\python.exe' 'Tools\core_freeze\e1b_v2\validate_e1b_v2.py'
```

默认输出到：

```text
outputs/e1b_taskset_v2_20260730/
```

验证器会检查任务数量、合同哈希、分区隔离、A003精度配对、条件配对，并逐条调用生产工具验证72个独立参考答案。该步骤不调用外部大模型API。

## 真实API冒烟

先生成只包含7条 `benefit_estimation` 任务的冻结快照：

```powershell
& '.\.venv\Scripts\python.exe' 'Tools\core_freeze\e1b_v2\prepare_e1b_v2_smoke.py'
```

再使用v2冒烟配置运行：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1b_pilot\run_e1b_pilot.py' `
  --tasks 'outputs\e1b_smoke_taskset_v2_20260730\e1b_smoke_tasks_v2.json' `
  --config 'Tools\core_freeze\e1b_v2\run_config_smoke_v2.json' `
  --output-dir 'outputs\e1b_v2_api_smoke_r1_20260730' `
  --repeats 1
```

配置明确设置 `gate_evaluation_opened=false`。运行器发现快照中含有任何 `gate_evaluation` 任务时会在API调用前拒绝执行。

## 完整收益估计运行

生成45条前置任务快照：

```powershell
& '.\.venv\Scripts\python.exe' 'Tools\core_freeze\e1b_v2\prepare_e1b_v2_benefit.py'
```

运行三次重复：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1b_pilot\run_e1b_pilot.py' `
  --tasks 'outputs\e1b_benefit_taskset_v2_20260730\e1b_benefit_tasks_v2.json' `
  --config 'Tools\core_freeze\e1b_v2\run_config_benefit_v2.json' `
  --output-dir 'outputs\e1b_v2_benefit_r3_20260730' `
  --repeats 3
```

执行按问题组聚类的专项分析：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1b_v2\analyze_e1b_v2_benefit.py' `
  'outputs\e1b_v2_benefit_r3_20260730' `
  --output-dir 'outputs\e1b_v2_benefit_analysis_r3_20260730'
```

## 候选门控策略冻结

在打开 `gate_evaluation` 之前，将开发集结论固化为机器可执行策略并生成回顾性拟合审计：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1b_v2\apply_candidate_gate_policy.py'
```

策略文件：

```text
Tools/core_freeze/e1b_v2/candidate_gate_policy_v1.json
```

默认审计输出：

```text
outputs/e1b_v2_candidate_gate_policy_v1_20260730/
```

策略只读取 `source_tool_id`、`precision_policy` 以及由输入数值直接派生的动态范围和是否需要归一化，不读取题号、题组、题面、化学式或期望答案。策略版本冻结后，`gate_evaluation` 结果不得回写或调整该版本；任何修改都必须产生新的策略版本，并且不能替代v1的独立后置评测结果。

## 独立Gate解封

策略v1已在Git提交`1ee098e`中冻结。生成27题Gate快照和API运行前动作清单：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1b_v2\prepare_e1b_v2_gate.py'
```

输出目录为：

```text
outputs/e1b_gate_taskset_v2_20260730/
```

该步骤将策略、运行配置、27题快照、预运行动作和准备器源码一并写入哈希清单。只有该准备包通过校验后，才可使用`run_config_gate_v2.json`进行真实API运行。
