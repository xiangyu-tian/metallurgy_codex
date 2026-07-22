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
  "mode": "autonomous",
  "model_code": null,
  "arguments": {"formula": "Fe2O3"},
  "llm_name": "external-orchestrator",
  "prompt_version": "v1",
  "result_validation_enabled": true
}
```

`mode` 取值：

- `direct`：禁止调用工具，保存直接回答基线；
- `forced`：必须提供 `model_code`，校验通过后调用；
- `autonomous`：按问题召回候选并决定是否调用，可用 `model_code` 固定候选以复现实验。

响应保存 `user_query`、大模型与 Prompt 版本、候选模型、选中模型、选择原因、生成参数、校验和执行结果、重试次数、最终回答、延迟与 Token 用量占位。

### `GET /api/v1/experiments/{experiment_id}`

读取单次实验完整轨迹。

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

测试包含 17 个黄金种子算例、完整模型卡检查、超过 100 个由协议自动生成的异常输入检查、数据库不可用兜底，以及三种实验模式的调用闭环。

黄金算例源文件：`Tools/benchmarks/golden_cases.json`。
