# E1b pilot v1

本目录把`verified_core v1`中的成功独立参考案例转换为E1b主要因果对比任务：

```text
Forced Verified Tool + Oracle Parameters
vs
No Tool
```

当前生成14个任务、28个条件运行单元（尚未乘以模型运行重复数）：

| 工具 | 任务数 |
| --- | ---: |
| A001 | 4 |
| A002 | 2 |
| A003 | 3 |
| A004 | 2 |
| B019 | 3 |

每条任务都绑定：

- 工具版本、合同ID和合同哈希；
- 独立参考案例；
- 规范输入和Oracle参数；
- 结构化答案Schema；
- 自动评分路径和预设容差；
- `no_tool`与`forced_verified_oracle_parameters`成对条件。

运行生成器：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1b_pilot\generate_e1b_pilot.py'
```

输出：

```text
outputs/e1b_pilot_v1_20260730/e1b_tasks.json
outputs/e1b_pilot_v1_20260730/generation_report.json
outputs/e1b_pilot_v1_20260730/artifact_manifest.json
```

`dataset_status=prepared`只表示任务、合同和评分接口可执行，不表示模型实验已运行，
也不表示任务数量足以进行正式功效检验。
