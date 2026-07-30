# E1b v2 真实API冒烟结果

日期：2026-07-30

状态：`descriptive_development_only`

本次只验证E1b v2任务、运行器、结构化评分和真实API链路能否共同工作，不进行确认性推断，不打开 `gate_evaluation`，不改变 `Core Frozen = false`。

## 运行范围

- 模型：`deepseek-v4-flash`
- Thinking：`disabled`
- 温度：0
- 重复：1次
- 数据分区：仅 `benefit_estimation`
- 任务：7条
- 条件单元：14个
- 覆盖工具：A001、A002、A003、A004、B019
- A003：同一Fe2O3基础问题的严格版和近似版
- B019：同一基础问题的fraction和percent标度

运行器在配置中固定 `gate_evaluation_opened=false`；如果任务快照混入后置评估任务，会在API调用前直接拒绝。

## 技术结果

| 指标 | 结果 |
| --- | ---: |
| 计划单元 | 14 |
| 完成单元 | 14 |
| 供应商失败 | 0 |
| 解析失败 | 0 |
| 完整配对 | 7/7 |
| 不完整配对 | 0 |

这说明v2新增的 `split`、`base_task_group_id` 和 `precision_policy` 可以贯穿任务快照、运行记录和分析报告。

## 正确率

| 条件 | 正确数 | 准确率 |
| --- | ---: | ---: |
| No Tool | 6/7 | 0.8571 |
| Forced Verified Tool | 7/7 | 1.0000 |
| 描述性配对增益 | 1/7 | +0.1429 |

唯一的正增益任务是：

```text
E1B2-A004-007
base_task_group_id = A004-TRACE
```

题目要求归一化：

```json
{"matrix": 999.0, "trace": 1.0}
```

No Tool输出：

```json
{"normalized":{"matrix":0.999,"trace":0.001001}}
```

独立参考和生产工具输出：

```json
{"normalized":{"matrix":0.999,"trace":0.001}}
```

因此，工具在本例中消除了一个微量组分的数值归一化错误。

## Fe2O3结果

严格版本：

```text
precision_policy = strict_versioned
abs_tol = 0.0001 g/mol
```

近似版本：

```text
precision_policy = approximate_educational
abs_tol = 0.1 g/mol
```

两种条件下模型都返回：

```json
{"molar_mass":159.687}
```

两类精度任务在No Tool和Forced Tool下均正确，本次没有观察到工具收益。这进一步说明：

> “是否应调用”不能仅由“这是摩尔质量计算”决定，而应结合精度合同、模型无工具错误率、风险和调用成本判断。

第一版开发任务曾观察到Fe2O3严格任务的工具收益；本次单次冒烟没有复现该错误。两者并不矛盾，而是说明单次回答具有波动，必须在更多独立任务和预注册重复上估计稳定收益。

## Token与延迟

| 条件 | 总Token | 平均延迟 |
| --- | ---: | ---: |
| No Tool | 1045 | 872.70 ms |
| Forced Verified Tool | 2028 | 972.64 ms |

Forced Tool条件因为携带工具结果，Token约为No Tool的1.94倍，平均延迟增加约99.94 ms。调用决策因此不能只比较正确率，还需要报告额外上下文和延迟成本。

## 当前判断

本次冒烟通过，可以进入45条 `benefit_estimation` 的完整开发运行准备阶段，但不能据7条单次结果冻结调用边界。

下一阶段应：

1. 保持27条 `gate_evaluation` 封存；
2. 对45条收益估计任务运行预定重复；
3. 按工具、基础问题组和精度政策汇总工具收益；
4. 形成初始调用边界规则；
5. 冻结规则后，才允许打开后置评估集检验泛化。

## 证据路径

- 任务快照：`outputs/e1b_smoke_taskset_v2_20260730/e1b_smoke_tasks_v2.json`
- 原始运行：`outputs/e1b_v2_api_smoke_r1_20260730/run_records.jsonl`
- 运行报告：`outputs/e1b_v2_api_smoke_r1_20260730/run_report.json`
- 分析报告：`outputs/e1b_v2_api_smoke_analysis_r2_20260730/analysis_report.json`
- 运行及分析清单：对应目录下的 `artifact_manifest.json`
