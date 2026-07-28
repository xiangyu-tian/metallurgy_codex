# CF-11产物契约、语义验收与最终化证据

> 后续最终化安全加固见`cf11_finalization_hardening_evidence_20260728.md`。

## 记录状态

- 日期：2026-07-28
- 统计接口：`1.0-rc1.1`
- GLMM规范：`1.0-rc1.1`
- 结论：上一轮复审提出的三项实现验收问题已关闭；CF-11整体继续保持`in_progress`

---

## 1. 正式产物契约

正式产物由20类扩展为30类，新增纳入：

- `h3_glmm_input.csv`
- `h4_glmm_input.csv`
- `h3_standardization.csv`
- `h4_standardization.csv`
- H3主要模型随机效应；
- H3 Schema敏感性随机效应；
- H3方法交互敏感性随机效应；
- H4主要模型随机效应；
- H4 Schema敏感性随机效应；
- `model_status.csv`。

这些文件均进入：

```text
FORMAL_OUTPUTS
confirmatory_report.json.artifact_files
artifact_manifest.csv
missing_outputs检查
```

因此，正式复核可以还原R实际接收的行、协变量标准化参数、随机效应方差和每个模型的最终状态。

---

## 2. 敏感性字段语义

政策字段改为：

```json
{
  "allowed_to_change_primary_support_classification": false,
  "observed_conclusion_differs_from_primary": null
}
```

前者表示预注册政策：敏感性结果不能改写主要支持等级。后者表示实际观察结果，在真实候选数据完成前保持`null`，不再预先硬编码为`false`。

---

## 3. 内容级语义验收

正式管线除检查文件存在外，还验证：

- 5个模型状态集合完整且唯一；
- H3/H4主要模型必须收敛；
- 敏感性模型只能是`converged`或显式`failed`；
- H3计划对比集合与预注册完全一致；
- H4恰好包含三个预注册对比；
- 收敛模型的估计量、双侧95%置信区间和p值均为有限数；
- H4 Holm结果可由原始单侧p值独立复算；
- H3交互敏感性覆盖全部四种正式方法；
- manifest文件集合和哈希可复算。

`emmeans`产生的置信区间列名在R层统一为：

```text
ci_lower
ci_upper
```

单侧方向仅用于p值，报告的95%置信区间为有限的双侧区间。

敏感性模型失败会留下模型状态、全部拟合尝试以及失败占位审计文件，但不会改变主要H3/H4结论。主要模型失败仍终止正式管线。

---

## 4. 独立最终化流程

新增：

- `Tools/core_freeze/finalize_cf11.py`
- `Tools/core_freeze/finalization_evidence_template.json`

两阶段流程为：

```text
formal_pipeline.py
→ 生成不可变分析报告和30类产物
→ cf11_status保持in_progress

finalize_cf11.py
→ 复算全部产物哈希
→ 校验真实候选干跑证据
→ 校验统计审查
→ 校验报告审查
→ 校验项目审批
→ 生成独立cf11_finalization_record.json
```

四份证据必须绑定相同的：

- 输入文件哈希；
- 分析Git提交；
- `artifact_manifest.csv`哈希；
- 审查人；
- ISO-8601签署时间。

最终化程序不修改原始`confirmatory_report.json`。即使最终化记录将CF-11记为`passed`，仍明确保持：

```text
core_frozen = false
```

因为CF-01至CF-10需要独立通过。

---

## 5. 测试记录

独立最终化测试：

```text
Ran 2 tests
OK
```

覆盖：

- 绑定完整签署证据后生成CF-11最终化记录；
- 任一分析产物被篡改后拒绝最终化。

五模型GLMM端到端测试：

```text
Ran 2 tests in 67.627s
OK
```

覆盖30类正式产物、模型状态、语义校验、Holm复算和manifest复核。

完整Core Freeze测试集：

```text
Ran 17 tests in 63.874s
OK
```

既有离线回归：

```text
Ran 44 tests
OK
Golden benchmark: 138 cases, 17 models, baseline 2.0.0
```

Python编译、R 4.6.1及13个锁定依赖、4个JSON文件和Markdown围栏检查均通过。

---

## 6. 当前状态

```yaml
design_specification: passed
estimand_definition: passed
sensitivity_specification: passed
engine_implementation: passed
synthetic_integration: passed
artifact_contract: passed
real_candidate_dry_run: pending
statistical_review: pending
report_review: pending
approval: pending
overall: in_progress
```

下一阶段仍是CF-01、CF-02真实候选任务和工具池构造，不是继续修改统计理论。
