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

## 开发性运行

冻结的非密钥运行配置位于`run_config_v1.json`。API密钥只从被忽略的本地环境读取，
不会写入任务、运行记录或manifest。

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1b_pilot\run_e1b_pilot.py' `
  --output-dir 'outputs\e1b_development_run'
```

运行器执行以下闭环：

```text
No Tool直接回答
vs
Oracle参数执行verified_core工具后回答
→ 严格提取单一JSON对象
→ 按预注册路径和容差评分
→ 按task × repeat配对
→ 保存原始回答、工具结果、Token、延迟和状态
```

每个新运行目录会封存任务、配置、运行器和评分器源码快照。早期未自动封存任务和
配置的运行可在源文件尚未改变时使用`seal_e1b_run.py`补充快照。

开发性描述分析：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1b_pilot\analyze_e1b_pilot.py' `
  'outputs\e1b_development_run' `
  --output-dir 'outputs\e1b_development_analysis'
```

该分析先验证运行manifest，再按任务聚合重复。它不执行确认性显著性检验。
