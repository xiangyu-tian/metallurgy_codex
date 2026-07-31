# v1.1 CF-04 E2模型策略开发先导结果

## 结论

E2模型策略的首轮开发先导已经执行完成：

```text
model_pilot_execution = completed
CF-04 = in_progress
CF-08 E2 component = in_progress
CF-09 E2 component = pending
Core Frozen = false
```

本轮证明模型能够读取版本化工具契约，并在不实际调用工具的情况下输出边界判断。但当前提示词和输出协议尚不能进入正式实验：严格Schema有效率只有`23.64%`，主要原因是模型将底层flag名称写入了聚合型`primary_status`；语义层还存在不支持系统与契约超域混淆、多标签遗漏和动作优先级错误。

本结果仅是开发诊断，不允许作确认性推断，也不改变原始严格得分。

## 1. 冻结执行条件

| 项目 | 值 |
|---|---|
| 数据集 | `E2-CONTRACT-BOUNDARY-PILOT-V1-20260731` |
| 任务数 | 55 |
| 重复数 | 1 |
| 模型 | `deepseek-v4-flash` |
| 接口 | `https://api.deepseek.com` |
| Thinking | disabled |
| 工具访问 | disabled |
| 提示词版本 | `e2-contract-readiness-v1` |
| 确认性推断 | false |

发送给模型的内容仅包括：

1. 当前任务对应的版本化工具契约视图；
2. 当前结构化请求；
3. 冻结的边界判断提示词。

`mutation_types`、`expected_flags`、任务ID和评分答案均未暴露给模型。

外部发送范围由用户在执行前明确授权，原始授权语句及成功运行manifest绑定保存在：

```text
Tools/core_freeze/e2_contract_boundaries/external_data_sharing_authorization_20260731.json
```

第一次在受限环境中的尝试被Windows套接字权限拦截，55条请求均未到达供应商。随后在用户明确授权的联网环境中使用相同冻结配置重新执行，成功运行保存在独立目录，没有覆盖失败记录。

## 2. API执行完整性

| 指标 | 结果 |
|---|---:|
| 任务单元 | 55 |
| 完成 | 55 |
| 供应商失败 | 0 |
| 重试任务 | 0 |
| API尝试总数 | 55 |
| 可解析JSON | 55 |
| flags字段合法 | 55 |
| action字段合法 | 55 |

因此，本轮不存在因网络失败、重试或JSON完全不可解析而造成的选择性缺失。

## 3. 严格预设评分

严格评分要求`flags`、聚合型`primary_status`和`action`三个字段同时满足冻结Schema。任一字段不合法，该任务的三个预测字段均按无效处理。

| 指标 | 严格结果 |
|---|---:|
| Schema有效率 | 23.64%（13/55） |
| flags完全匹配率 | 20.00%（11/55） |
| flags平均Jaccard | 21.82% |
| 支持类别Macro-F1 | 14.16% |
| primary status准确率 | 18.18% |
| action准确率 | 20.00% |
| Invalid Execution Rate | 0.00% |
| Premature Call Rate | 0.00% |
| OOD Call Rate | 0.00% |

该表是本轮唯一的原始严格得分，后续诊断不能替代它。

## 4. 独立字段开发诊断

55条响应均为可解析JSON。42条严格无效样本的共同问题是：

```json
{
  "flags": ["missing_parameter"],
  "primary_status": "missing_parameter",
  "action": "clarify"
}
```

其中`flags`和`action`均正确，但冻结Schema要求：

```json
{
  "flags": ["missing_parameter"],
  "primary_status": "missing_or_ambiguous_input",
  "action": "clarify"
}
```

为定位开发问题，分析脚本在不改变严格得分的前提下，独立检查各字段，并按冻结优先级从模型预测flags派生诊断状态和动作：

| 诊断指标 | 结果 |
|---|---:|
| flags字段合法率 | 100.00% |
| action字段合法率 | 100.00% |
| primary status字段合法率 | 23.64% |
| flags完全匹配率 | 76.36%（42/55） |
| flags平均Jaccard | 83.64% |
| 原始action准确率 | 89.09%（49/55） |
| 由预测flags派生的primary准确率 | 89.09% |
| 由预测flags派生的action准确率 | 90.91% |

错误计数：

| 错误类型 | 数量 |
|---|---:|
| 严格Schema无效 | 42 |
| 聚合状态映射错误 | 42 |
| flags不完全匹配 | 13 |
| action错误 | 6 |

这些结果只用于区分“输出协议失败”和“边界语义失败”，不是后验改分。

## 5. 语义错误结构

### 5.1 单因素任务

ready、缺参、歧义、契约超域、不可用和版本错配任务的底层flags均达到`100%`完全匹配。

主要例外是：

```text
unsupported_system / unsupported_phase
→ 模型常输出 contract_defined_out_of_domain
```

该错误通常不改变`refuse`动作，但会破坏可追溯的错误原因和细粒度统计。

### 5.2 多标签任务

`ambiguous_parameter + contract_defined_out_of_domain`是最明显的薄弱组：

| 指标 | 结果 |
|---|---:|
| 任务数 | 5 |
| flags完全匹配率 | 0% |
| 原始action准确率 | 20% |

模型常只保留超域flag，遗漏更高优先级的歧义flag，进而输出`refuse`而不是`clarify`。

另外：

- `missing_parameter + unavailable`：flags完全匹配率80%，原始action准确率60%；
- `contract OOD + unavailable`：flags完全匹配率60%，原始action准确率100%。

这表明动作层的主要风险不是错误调用，而是多标签条件下没有稳定执行“先追问还是直接拒绝”的优先级。

## 6. 当前研究含义

本轮不能支持“模型边界策略已经有效”，也不能用严格20%的表面准确率直接断言模型完全不会判断边界。

更准确的结论是：

1. 模型能识别多数单因素底层边界事实；
2. 当前输出契约同时要求底层flags和聚合状态，提示词没有让模型稳定完成两层映射；
3. 不支持系统与一般契约超域的细粒度区分仍不可靠；
4. 多标签完整保留及动作优先级是E2必须单独测量的核心能力；
5. 单次55任务开发先导不能估计模型重复波动，也不能支持E2样本量冻结。

## 7. 版本治理

本轮运行配置固定：

```text
model_policy_revision_allowed = false
```

其含义是不得修改本轮提示词后覆盖原结果，也不得用诊断派生值替代严格得分。若进入下一开发版本，必须：

1. 创建新的提示词和Schema版本；
2. 使用新的运行配置与执行授权；
3. 保留本轮所有原始产物和哈希；
4. 使用独立输出目录；
5. 明确区分开发比较与正式确认性实验。

下一版本可以考虑将`primary_status`改为由程序根据flags确定性派生，避免要求模型重复输出可计算字段；这属于新策略候选，不是对本轮结果的修补。

## 8. 产物

成功运行：

```text
outputs/v11_cf04_e2_model_development_r1_network_retry_20260731/
├── run_records.jsonl
├── run_report.json
├── artifact_manifest.json
├── task_source_snapshot.json
├── contracts_snapshot.json
├── policy_snapshot.json
├── prompt_source_snapshot.json
├── output_schema_snapshot.json
├── run_config_snapshot.json
├── execution_authorization_snapshot.json
└── runner_source_snapshot.py
```

独立诊断：

```text
outputs/v11_cf04_e2_model_development_analysis_20260731/
├── task_diagnostics.csv
├── mutation_summary.csv
├── analysis_report.json
└── artifact_manifest.json
```

分析manifest绑定了原始`run_records.jsonl`、`run_report.json`、原运行manifest和分析脚本的SHA-256。

## 9. 自动测试

本轮新增测试覆盖：

1. 冻结输入和执行授权的精确哈希绑定；
2. 运行入口必须执行授权校验；
3. 提示词不得泄露变换类型、预期标签和任务ID；
4. 输出Schema、严格多标签评分和供应商失败处理；
5. 离线55任务完整运行；
6. 独立字段诊断不得修改严格得分；
7. 分析manifest绑定和密钥泄漏检查。

测试结果：

```text
E2模型运行与诊断定向测试：12 passed
Core Freeze完整回归：126 passed
```

## 10. 下一步

CF-04继续保持`in_progress`。下一步应：

1. 冻结E2策略候选v1.1，将聚合状态和动作改为由flags确定性派生；
2. 加强“不支持系统”和“一般超域”的契约字段定义；
3. 为多标签完整保留和优先级增加明确机器测试；
4. 补入温度、压力和模型卡OOD契约；
5. 使用新版本做独立开发复核，再据重复波动规划E2正式样本量。
