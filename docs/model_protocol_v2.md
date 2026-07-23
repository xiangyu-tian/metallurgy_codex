# Metallurgy Platform v2.0 统一模型协议

## 实施边界

本协议冻结当前 17 个模型（A001–A005、B001–B009 中已实现项、B019、C001–C002），保留旧 `/invoke` 接口，并以新增接口承载校验、执行追踪和大模型实验。新增模型只需继承 `BaseModelTool` 并声明模型卡，无需修改注册中心。

## 模型卡

每张模型卡至少包含：

`model_code`、`model_name`、`category`、`description`、`input_schema`、`output_schema`、`input_units`、`output_units`、`applicable_conditions`、`temperature_range`、`pressure_range`、`required_data`、`data_source`、`formula_reference`、`dependencies`、`version`、`status`、`error_codes`。

旧字段 `model_id`、`name`、`scenario`、`input_schema_json`、`output_schema_json` 保留，供现有前端和数据库兼容使用。

## 接口契约

### `GET /api/v1/models`

返回全部模型卡。可使用 `scenario` 查询参数筛选。

### `GET /api/v1/models/{model_code}`

返回单个模型卡；不存在时返回 HTTP 404。

### `POST /api/v1/models/{model_code}/validate`

请求：

```json
{
  "input": {"formula": "Fe2O3"}
}
```

响应：

```json
{
  "valid": true,
  "model_code": "A003",
  "model_version": "1.0.0",
  "errors": []
}
```

该接口只检查参数完整性、类型、枚举和模型声明的数值范围，不执行公式。

### `POST /api/v1/models/{model_code}/execute`

请求：

```json
{
  "input": {"formula": "Fe2O3"},
  "options": {
    "validate_boundary": true,
    "return_provenance": true
  }
}
```

响应包含 `execution_id`、`trace_id`、`model_code`、`model_version`、标准化输入、实际数据记录、边界检查、输出、状态、标准错误码、运行时间和调用主体。

### `GET /api/v1/executions/{execution_id}`

读取已完成的执行轨迹。默认存储模式为 PostgreSQL 持久化并带进程内回退；执行迁移 `003_model_experiments.sql` 后，服务重启仍可读取历史记录。

### `POST /api/v1/experiments/run`

请求：

```json
{
  "user_query": "请计算 Fe2O3 的摩尔质量",
  "engine": "deepseek",
  "mode": "autonomous",
  "model_code": null,
  "arguments": {},
  "llm_name": "deepseek-v4-flash",
  "prompt_version": "m4.5-v1",
  "result_validation_enabled": true
}
```

`mode` 取值：

- `direct`：禁止调用工具，保存直接回答基线；
- `forced`：必须提供 `model_code`，校验通过后调用；
- `autonomous`：按问题召回候选并决定是否调用，可用 `model_code` 固定候选以复现实验。

`engine` 取 `deterministic`（默认，可复现基线）或 `deepseek`（真实 Function Calling）。真实引擎不会读取基准数据的 `standard_arguments`：参数只能由 DeepSeek 从用户问题生成。`forced` 只暴露指定模型，`autonomous` 暴露全部 17 张模型卡，`direct` 不暴露工具。工具执行结果以 `role=tool` 回传给 DeepSeek 后再生成最终回答。

响应保存 `user_query`、实验引擎、大模型与 Prompt 版本、候选模型、选中模型、生成参数、校验和执行结果、完整多工具调用链、脱敏的两阶段 LLM 轨迹、响应编号、最终回答、延迟与真实 Token 用量。迁移 `004_real_llm_experiments.sql` 为这些字段提供 PostgreSQL 持久化。

### `GET /api/v1/experiments/{experiment_id}`

读取单次实验完整轨迹。

## 工具调用基准数据集

固化数据文件：`Tools/benchmarks/tool_calling_cases.json`；生成器：`Tools/benchmarks/build_tool_calling_dataset.py`。数据集版本为 `1.1.0`，Schema 版本为 `1.1`，共 120 条，覆盖：

- 不调用工具 `no_tool`：15 条；
- 单工具 `single_tool`：51 条；
- 多工具 `multi_tool`：15 条；
- 信息不足 `insufficient_info`：15 条；
- 超适用域 `out_of_domain`：14 条；
- 对抗问题 `adversarial`：10 条。

每条样本包含自然语言问题、是否调用标签、候选与标准模型、标准参数及单位、多步参数与标准调用序列、标准答案、期望结果及容差、适用条件、难度、干扰因素、参考依据和期望处理结果。同一份数据不绑定具体大模型，可重复用于 `direct`、`forced`、`autonomous` 三种模式，以及不同大模型和 Prompt 版本。

评价契约额外包含：

- `expected_final_behavior`：期望的最终行为，如概念回答、澄清、拒绝或数值回答；
- `acceptable_actions`：语义上允许的终止动作，例如超适用域同时允许直接拒绝和工具校验后拒绝；
- `answer_requirements`：答案自动评价方式，支持数值容差、概念术语组和行为评价；复杂多工具答案标记为 `manual`。

120 条中有 56 条数值答案、29 条澄清/拒绝行为、20 条概念答案可自动评价；15 条复杂多工具答案进入人工评价，不计入自动答案准确率分母。

### `GET /api/v1/benchmarks/tool-calling`

返回数据集摘要和算例列表。支持 `category`、`difficulty`、`limit` 查询参数。

### `GET /api/v1/benchmarks/tool-calling/{case_id}`

返回指定算例的完整标准标签。

### `POST /api/v1/benchmarks/tool-calling/run`

批量运行选定算例：

```json
{
  "engine": "deepseek",
  "modes": ["direct", "forced", "autonomous"],
  "case_ids": ["TC-NO_TOOL-001", "TC-SINGLE_TOOL-001"],
  "categories": [],
  "difficulties": [],
  "max_cases": 120,
  "llm_name": "deepseek-v4-flash",
  "prompt_version": "m4.5-v1",
  "result_validation_enabled": true
}
```

响应包含批次编号、运行配置、全局/分模式/分类别汇总以及逐条实验记录号。M4.5.1 将评价拆为三条互不替代的轴：

- `final_answer_correct` / `semantic_case_passed`：最终文字答案是否满足数值、概念或行为要求；
- `final_behavior_correct`：回答、澄清、直接拒绝、工具拒绝等终止行为是否合理；
- `path_compliance_correct`：是否按冻结的标准工具、参数、顺序和执行结果完成调用。

`strict_case_passed` 要求答案、行为和标准路径同时通过；`case_passed` 是 `semantic_case_passed` 的兼容别名。无法自动评价的复杂答案返回 `null`，并计入 `manual_review_experiment_count`，不会污染准确率分母。其他诊断指标继续包含是否调用判断、模型选择、参数精确匹配、单位处理、适用域校验、数值执行结果、调用链召回率、无效/重复调用率、平均调用次数、Token 和延迟。供应商请求失败单独计入 `failed_experiment_count`，不会被误判成“不调用工具”的正确决策。每条评分通过 `benchmark_case_id` 与实验轨迹关联，批次编号和数据集版本随评分写入 `experiment_run.metrics_json`。

确定性编排基线与 DeepSeek 真实引擎共用同一数据集、执行器和指标契约，可通过 `engine` 切换后直接对比。

## 大模型服务配置

现有 Node 后端聊天接口统一使用 DeepSeek 的 OpenAI 兼容格式，覆盖主聊天、小模型共享对话和独立工具对话三个入口。复制 `backend/.env.example` 为本机 `backend/.env` 后配置：

- `DEEPSEEK_API_KEY`：仅保存在被 Git 忽略的本机文件；
- `DEEPSEEK_OPENAI_BASE_URL`：Node 后端实际调用地址；
- `DEEPSEEK_ANTHROPIC_BASE_URL`：供 Anthropic 兼容客户端使用；
- `DEEPSEEK_MODEL`：当前实验模型；
- `DEEPSEEK_THINKING`：`enabled` 或 `disabled`。

`GET /api/health` 只返回提供商、模型、兼容地址和“密钥是否已配置”，不会返回密钥内容。聊天响应的 `data.llm` 保存实际模型、响应编号和 Token 用量，便于后续实验追踪。Python 模型服务从同一份本机配置读取 OpenAI 兼容地址，并已接入单次实验和批量评测接口。

M4.5.1 真实小批量复验（`deepseek-v4-flash`、`autonomous`、六类各 1 条）完成 6/6 请求：5 条可自动评价样本的语义答案和最终行为全部通过，1 条复杂多工具答案进入人工评价；标准工具路径为 5/6。唯一的路径差异仍是超适用域样本被模型直接合理拒绝，而冻结路径要求调用 A001 后由执行器拒绝。新评价契约将该样本记录为“语义通过、路径不一致”，不再把两种结论混为一次失败。

## 轨迹存储配置

数据库连接使用 libpq 标准环境变量：`PGHOST`、`PGPORT`、`PGDATABASE`、`PGUSER`、`PGPASSWORD`，也支持 `DATABASE_URL` 或 `POSTGRES_DSN`。源码不内置服务器地址。

`MODEL_TRACE_STORE` 支持三种取值：

- `auto`（默认）：写入 PostgreSQL，同时保留内存副本；数据库不可用时自动回退。
- `postgres`：强制使用 PostgreSQL，持久化失败直接报错。
- `memory`：仅进程内保存，适用于离线测试。

健康检查 `GET /api/v1/health` 的 `trace_store` 字段会显示当前持久化状态及回退原因。

以上接口同时提供不带 `/v1` 的兼容路径。

## 标准错误码

`INVALID_INPUT`、`UNIT_MISMATCH`、`OUT_OF_DOMAIN`、`MISSING_DATA`、`MULTIPLE_SPECIES_MATCH`、`PHASE_MISMATCH`、`TEMPERATURE_RANGE_ERROR`、`REACTION_NOT_BALANCED`、`NUMERICAL_ERROR`、`MODEL_NOT_APPLICABLE`、`UNKNOWN_MODEL`、`INTERNAL_ERROR`。

历史错误码在注册中心统一归一化，不要求 17 个旧模型同时重写。

## 自动验证

运行：

```powershell
python Tools/run_baseline_tests.py
```

测试包含 138 条实体黄金数值算例、120 条六类工具调用算例、完整模型卡检查、超过 100 个由协议自动生成的异常输入检查、数据库不可用兜底，以及三种实验模式的调用与自动评分闭环。黄金算例覆盖全部 17 个模型，每条均保存参考依据、适用条件和数值容差。

黄金算例源文件：`Tools/benchmarks/golden_cases.json`。
生成器：`Tools/benchmarks/build_golden_cases.py`；生成器使用独立解析公式与冻结的 IUPAC/NIST 常数，不调用模型注册表计算期望值。
