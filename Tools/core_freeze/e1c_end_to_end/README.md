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

## 准备后置评测开启包

完整开发运行通过后，使用以下命令在本地提取并冻结36道后置任务：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\e1c_end_to_end\prepare_e1c_evaluation.py'
```

开启包：

```text
outputs/e1c_evaluation_open_v1_20260731/
```

准备器会验证完整开发运行、开发产物manifest、协议、提示词、策略和源任务集哈希。开启包固定：

- 36道`end_to_end_evaluation`任务；
- 6个条件和216个计划单元；
- 评测运行配置；
- 评测模式运行器和评分器快照；
- 开启记录；
- 外部执行授权请求；
- 完整产物manifest。

生成开启包只表示本地评测快照已经打开，不代表允许向外部API发送数据。默认状态必须保持：

```text
external_api_execution_authorized = false
api_model_runs_performed = false
```

## 执行后置评测

后置评测必须先取得针对`execution_authorization_request.json`所列精确载荷的用户授权，再生成独立的`execution_authorization.json`。运行器会校验：

- 题目快照SHA-256；
- 提示词SHA-256；
- 运行配置SHA-256；
- 运行器SHA-256；
- 数据集、模型、端点和任务数。

缺少授权、授权决策不正确或任一哈希不一致时，运行器必须拒绝执行。正式评测禁止使用`--max-tasks`、`--conditions`或不同于冻结配置的重复次数。
