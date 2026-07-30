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
