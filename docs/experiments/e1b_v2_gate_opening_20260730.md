# E1b v2独立Gate解封记录

- Gate数据集：`E1B-TASKSET-V2-GATE-20260730`
- 冻结策略：`E1B-CANDIDATE-GATE-POLICY-V1`
- 策略SHA-256：`4d34ddc0a8d53d46f0aabf1469469dab243b9ddb6c03a5e8e849b9763801c1d5`
- 策略冻结提交：`1ee098e`
- Gate状态：已解封，尚未执行API
- 推断性质：独立后置开发评测，不是确认性实验

## 解封前提

候选策略v1已经先于Gate解封完成Git提交和远程备份。解封程序会拒绝以下情况：

- 完整72题源快照的SHA-256发生变化；
- 策略v1的SHA-256发生变化；
- 运行配置未选择`gate_evaluation`；
- 运行配置没有显式打开Gate；
- 配置允许修改策略；
- benefit与Gate的`base_task_group_id`存在重叠。

## Gate规模

| 工具 | 任务数 |
| --- | ---: |
| A001 | 6 |
| A002 | 5 |
| A003 | 8 |
| A004 | 4 |
| B019 | 4 |
| 合计 | 27 |

共有16个独立基础题组。两个条件、三次重复对应162个API单元。

## API运行前策略动作

在任何Gate API调用前已经生成27题动作：

| 动作 | 任务数 |
| --- | ---: |
| `CALL_VERIFIED_TOOL` | 4 |
| `ANSWER_WITHOUT_TOOL` | 23 |

4个调用任务全部由`CGP-V1-STRICT-VERSIONED`规则触发。Gate集中没有满足“高动态范围且需要重标度”的A004任务，因此本次后置集不能独立评价该规则。这一覆盖限制必须在结果报告中保留，不能把该规则记为通过。

## 冻结证据

准备包位于：

```text
outputs/e1b_gate_taskset_v2_20260730/
```

其中包括：

- `e1b_gate_tasks_v2.json`；
- `pre_run_policy_assignments.csv`；
- `candidate_gate_policy_v1.json`；
- `run_config_gate_v2.json`；
- `gate_preparer_source_snapshot.py`；
- `gate_opening_report.json`；
- `artifact_manifest.json`。

准备包明确记录`api_model_runs_performed=false`，因此它是API运行前证据，不与后续模型输出混合。
