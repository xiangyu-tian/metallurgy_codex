# CF-11估计目标与敏感性分析实现证据

> 后续产物与最终化验收补充见`cf11_artifact_finalization_evidence_20260728.md`。本文件中的20类产物是该轮提交时的历史契约，当前正式契约已扩展为30类。

## 记录状态

- 日期：2026-07-28
- 统计接口：`1.0-rc1.1`
- GLMM规范：`1.0-rc1.1`
- 协议：`1.0-rc3.1`
- 结论：估计目标和两类敏感性分析已冻结并通过合成数据端到端测试；CF-11继续保持`in_progress`

---

## 1. 主要估计目标

`schema_token_count`可能处于以下因果路径：

```text
路由方法
→ Schema暴露长度
→ 工具选择性能
```

因此，H3和H4主要模型不再控制`schema_token_count_z`。主要结果估计路由方法在实际Schema暴露机制下的总效应，包括层次化方法通过减少Schema暴露获得的效果。

主要模型继续控制任务难度：

```text
difficulty_score_z
```

主要H3结论固定为四种非Oracle方法等权平均后的近邻干扰效应。它不声称四种方法的条件效应相同。

---

## 2. 预注册敏感性分析

### 2.1 Schema调整敏感性

H3和H4分别在主要模型结构上加入：

```text
schema_token_count_z
```

用于估计固定Schema长度后的直接效应。该结果只用于判断主要结论对Schema调整是否敏感，不能替代主要模型，也不能改变H4主要支持等级。

### 2.2 H3方法异质性

H3增加：

```text
method × neighbor_condition
```

并逐方法报告：

```text
functional_overlap_8 − lexical_8
```

该分析检查跨方法平均效应是否由单一方法主导，不要求每个方法分别显著，也不改变H3主要确认性检验。

---

## 3. 正式产物扩展

在原13类正式产物基础上新增：

- `h3_schema_adjusted_sensitivity_glmm_fixed_effects.csv`
- `h3_schema_adjusted_sensitivity_contrasts.csv`
- `h3_method_interaction_sensitivity_glmm_fixed_effects.csv`
- `h3_method_interaction_sensitivity_contrasts.csv`
- `h4_schema_adjusted_sensitivity_glmm_fixed_effects.csv`
- `h4_schema_adjusted_sensitivity_contrasts.csv`

同时新增`artifact_manifest.csv`，记录除自身外全部正式产物的SHA-256。正式产物契约现为20类。`model_attempts.csv`同时记录5个模型的公式、优化器、收敛码、梯度、Hessian、奇异拟合和随机效应简化状态。

`confirmatory_report.json`明确记录：

```text
primary.effect = total_method_effect
primary.schema_token_count_adjusted = false
sensitivity.schema_token_count_adjusted = true
sensitivity.h3_method_by_neighbor_interaction = true
sensitivity.changes_primary_support_classification = false
```

最终报告另外记录输入文件哈希、`r_engine_lock.json`哈希、分析Git提交和已跟踪工作区清洁状态。

---

## 4. 合成数据端到端测试

执行：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest `
  'Tools.core_freeze.tests.test_glmm_engine' -v
```

结果：

```text
Ran 2 tests in 61.120s
OK
```

新增断言包括：

- H3/H4主要公式不含`schema_token_count_z`；
- H3/H4 Schema敏感性公式包含`schema_token_count_z`；
- H3交互敏感性公式包含`method × neighbor_condition`；
- H3交互敏感性输出覆盖全部四种正式方法；
- 20类正式产物全部生成；
- CF-11细分状态正确，真实候选数据干跑仍为`pending`。

完整Core Freeze测试集：

```text
Ran 15 tests in 67.159s
OK
```

既有离线回归：

```text
Ran 44 tests
OK
Golden benchmark: 138 cases, 17 models, baseline 2.0.0
```

R 4.6.1及锁文件中的13个依赖版本检查全部通过；JSON结构和Markdown围栏检查通过。

---

## 5. 当前冻结判断

```yaml
design_specification: passed
engine_implementation: passed
synthetic_integration: passed
real_candidate_dry_run: pending
statistical_review: pending
report_review: pending
approval: pending
overall: in_progress
```

真实候选数据形成前，不生成真实效果结论，不把合成测试结果用于支持H3或H4，也不申请`Core Frozen`。
