# v1.1 CF-06 Full Schema API 可行性实测结果（R1）

## 1. 结论

冻结的 10 个请求已于 2026-08-09 使用 `deepseek-v4-flash` 完成单次开发性可行性实测：

```yaml
request_count: 10
accepted_count: 10
provider_failure_count: 0
provider_retry_count: 0
tool_calls_executed: 0
fallbacks_applied: 0
confirmatory_inference_allowed: false
CF-06: passed
Core Frozen: false
```

17、50、100、120 四种规模的 OpenAI 格式函数 Schema 均被 API 原样接受。在 `tool_choice=auto` 条件下，四种规模均返回一个原生函数调用，目标均为 `A003`，参数均为 `{"formula":"Fe2O3"}`。

本次通过只证明供应商接口、请求规模、Token、延迟和调用格式在冻结探针上可行，不证明 120 个工具均已科学验证，也不构成 E3 路由准确率的确认性结论。

## 2. 实测结果

| 工具数 | API接受 | Prompt Token | 相对无工具基线的Schema Token增量 | 延迟（ms） | A003选择 | 参数正确 |
|---:|---|---:|---:|---:|---|---|
| 17 | 是 | 3,336 | 3,273 | 1,220.53 | 是 | 是 |
| 50 | 是 | 8,760 | 8,697 | 1,180.98 | 是 | 是 |
| 100 | 是 | 17,204 | 17,141 | 894.45 | 是 | 是 |
| 120 | 是 | 20,602 | 20,539 | 1,946.27 | 是 | 是 |

无工具的同提示基线为 63 Prompt Token。最大规模 120 工具的请求实际使用 20,602 Prompt Token，未触发接口拒绝、上下文错误或函数数量错误。

## 3. `tool_choice=none` 的供应商行为

四种规模的 `tool_choice=none` 请求均被 API 接受，并且均未返回工具调用。但是：

- 四个请求的 Prompt Token 都是 95；
- 相对同提示无工具基线的 Token 增量均为 0；
- 模型均报告目标工具不可见；
- 模型能够复述用户提示中明示的工具数量，但不能识别 Schema 中的 `A003`。

因此，当前 DeepSeek 接口中的 `tool_choice=none` 应解释为：

> 禁止工具调用，同时函数 Schema 没有作为模型可见上下文计入本次请求。

后续不得把该条件表述为“模型读取了完整 Schema，但被禁止调用”。如果实验需要在模型可见 Schema 的情况下观察调用决策，应使用 `tool_choice=auto`，截获并记录工具调用而不执行；如果需要纯 No Tool/Blind 对照，则直接不发送 `tools`。

## 4. 验收边界

本轮支持：

1. 17/50/100/120 个函数 Schema 可以提交给当前供应商；
2. 120 工具请求可以获得原生函数调用响应；
3. 实际 Prompt Token、延迟、错误和工具调用结构能够按请求记录；
4. 返回的工具调用可以只记录而不执行；
5. `tool_choice=none` 的实际行为已经实测并形成限制声明。

本轮不支持：

1. 120 个目录条目已经全部可执行或科学正确；
2. A003 在大工具池中的一次成功等价于稳定路由性能；
3. 不同规模之间存在统计显著差异；
4. CF-05、CF-08、CF-09 或 Core Frozen 已完成。

## 5. 审计证据

```yaml
opening_commit: 01dfb4b323bcce8127217509729929b43631bb1b
request_bundle_sha256: 68887ca56de6a990fde781d512085ad63794f16f7cbde548ed0e925a1b41ad95
authorization_sha256: ed73e4c3ff79f4fc5c00c693ee937efade9be8d878f78514f624c641d0c57be9
runtime_manifest_sha256: f209ee31c076c8fea01000018a2c80563915449b1bd16e0a2a6b8482d50bf6c3
request_results_sha256: 30215c7e6e3e7cce27fa69f8d12e8bc1b2a756bc585ea0d6cc70dfd4470997c3
runtime_report_sha256: e54425d0040afe5b63ca69f62be8d0f7439d2f19f2ec01d933323c37962a23bd
runtime_artifact_count: 7
runtime_manifest_verification_failures: 0
```

运行目录：

```text
outputs/v11_cf06_full_schema_api_runtime_r1_20260809/
```

## 6. 下一步

CF-06 不再需要重复进行相同的单次可行性调用。下一主线返回 CF-05：继续扩充目标工具的独立契约近邻并形成更多可用的 0/4/8 控制池；CF-06 的 Token 与延迟结果同时作为后续 E3 先导和资源预算输入。
