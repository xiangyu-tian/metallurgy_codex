# v1.1 CF-06 Full Schema API可行性开启包v1

## 1. 当前结论

```yaml
opening_id: V11-CF06-FULL-SCHEMA-API-OPENING-V1-20260809
status: offline_preflight_passed_awaiting_explicit_api_authorization
provider: deepseek
model: deepseek-v4-flash
pool_sizes: [17, 50, 100, 120]
scheduled_request_count: 10
external_api_calls: 0
external_api_execution_authorized: false
tool_execution_allowed: false
confirmatory_inference_allowed: false
cf06_status: in_progress
core_frozen: false
```

本阶段只完成离线请求构建、Schema结构审计、授权门和模拟传输测试。没有向DeepSeek发送任务、提示词或工具Schema。

## 2. 供应商约束快照

2026-08-09核对DeepSeek官方资料：

- Chat Completion原生支持Function Calling和`tool_choice=none/auto/required`；
- 单次请求最多支持128个函数；
- `deepseek-v4-flash`官方上下文长度为1M Token；
- 本次使用OpenAI兼容地址`https://api.deepseek.com`和非思考模式。

来源：

- [Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)
- [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)
- [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)

这些限制作为运行前供应商快照，不替代实际API响应。120函数小于文档声明的128函数上限，但只有授权后的实际请求才能证明当前账户、模型和请求载荷确实可执行。

## 3. 冻结请求矩阵

共10次请求：

1. `auto_function_call`同提示、无工具基线1次；
2. `none_schema_visibility`同提示、无工具基线1次；
3. 17、50、100、120工具下`tool_choice=auto`各1次；
4. 17、50、100、120工具下`tool_choice=none`各1次。

`auto`请求要求模型返回A003对`Fe2O3`的一次函数调用，但不执行工具。`none`请求检查模型是否遵守禁止调用，并以结构化内容报告A003及工具数量。

API是否接受完整请求是主要工程判据；A003是否选对属于行为诊断，不能把工具错选误报成“API不支持120 Schema”。

## 4. Token测量契约

未使用不匹配的本地Tokenizer伪装DeepSeek精确Token数。

授权运行后固定使用：

```text
总请求Token = provider usage.prompt_tokens

Schema暴露Token增量
= 同提示含工具请求的prompt_tokens
− 同提示无工具基线的prompt_tokens
```

离线阶段只记录规范化JSON字符数和UTF-8字节数：

| 工具数 | 参数字段数 | Schema字符数 | Schema UTF-8字节数 |
| ---: | ---: | ---: | ---: |
| 17 | 52 | 7,867 | 11,264 |
| 50 | 118 | 21,411 | 33,610 |
| 100 | 218 | 42,313 | 68,605 |
| 120 | 258 | 50,834 | 83,056 |

这些数字用于载荷审计，不声称等于模型Token数。

## 5. 失败与降级规则

- 每个冻结请求只执行一次；
- 供应商拒绝后不得减少工具数量重试；
- 不得临时改用文本工具目录；
- 不执行模型返回的任何函数调用；
- 保留每个请求的错误、响应、Token用量和延迟；
- `tool_choice=none`返回工具调用时必须作为协议行为异常报告；
- 本次结果只用于CF-06工程可行性，不进入H3/H4效果结论。

## 6. 验证结果

```yaml
new_cf06_tests: 11/11 passed
joint_cf06_catalog_a003_regression: 28/28 passed
artifact_count: 9
artifact_manifest_sha256: dd5e503bbe6503e0c6263e7dc84ec142482870b356fceadc5232967491809d4b
authorization_request_sha256: fb19b28873fbf5e36066bea9936bd47bbb2cb78c8cdbb4b44099a608a16d2464
provider_environment_ready: true
api_key_written_to_artifacts: false
```

## 7. 下一门槛

执行前必须由用户明确授权以下外部发送范围：

- 两个中性探针提示；
- 17/50/100/120四组OpenAI格式函数Schema；
- 共10个冻结Chat Completion请求；
- 不调用任何冶金工具，不进行确认性推断。

授权必须绑定开启包中的请求、配置、提示词、运行器和目录清单哈希。待授权并实测后，CF-06仍需结果审查，不能由运行器自行标记为`passed`。
