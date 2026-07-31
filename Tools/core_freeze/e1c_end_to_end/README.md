# E1c端到端损失分解

本目录将E1b得到的候选调用边界扩展为六条件端到端实验，用于区分边界判断、工具选择、参数生成、工具执行和结果表达损失。

## 生成并验证任务

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1c_end_to_end\generate_e1c_tasks.py'

& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1c_end_to_end\validate_e1c_tasks.py'
```

完整任务包：

```text
outputs/e1c_taskset_v1_20260731/
```

其中包含24题`runner_development`和36题`end_to_end_evaluation`。后置分区在提示词、运行器和评分器冻结前不得执行API。

## 准备开发快照

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1c_end_to_end\prepare_e1c_development.py'
```

开发快照：

```text
outputs/e1c_development_v1_20260731/
```

该目录只包含24道开发题，并绑定协议、提示词、运行配置、E1b策略、运行器和评分器源码。

## 六个条件

```text
no_tool
forced_verified_oracle_parameters
model_gate_oracle_parameters
oracle_gate_model_parameters
direct_fc
boundary_guided_fc
```

详细定义见`protocol_v1.md`。

## 开发运行

完整24题、单次重复会产生144个条件单元。首次真实API运行应先使用`--max-tasks`进行小规模连通性检查：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1c_end_to_end\run_e1c.py' `
  --tasks 'outputs\e1c_development_v1_20260731\e1c_development_tasks_v1.json' `
  --prompts 'Tools\core_freeze\e1c_end_to_end\prompts_v1.json' `
  --config 'Tools\core_freeze\e1c_end_to_end\run_config_development_v1.json' `
  --output-dir 'outputs\e1c_development_smoke_r1_20260731' `
  --repeats 1 `
  --max-tasks 2
```

只有开发运行的接口、解析和错误归因通过后，才能讨论解封36题后置分区。开发结果不得用于修改E1b策略v1。
