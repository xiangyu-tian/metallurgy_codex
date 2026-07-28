# H3/H4 GLMM引擎实现规范 v1.0-rc1.1

## 文档状态

- 版本：`1.0-rc1.1`
- 日期：2026-07-28
- 上位统计接口：`statistical_analysis_interface_v1.0-rc1.1.md`
- 状态：正式实现候选版；待真实候选数据干跑和统计审查

本文冻结统计引擎、主要估计目标、模型参数化、方法权重、敏感性分析、收敛判定、简化链和H4支持等级。本文不改变H1—H4或工具池设计。

---

## 1. 引擎与版本

```text
R: 4.6.1
lme4: 2.0-6
emmeans: 2.0.4
family: binomial
link: logit
likelihood approximation: Laplace
nAGQ: 1
```

完整依赖版本记录在`Tools/core_freeze/r_engine_lock.json`。正式运行前必须逐项验证版本；不允许自动升级后继续生成确认性结果。

选择`lme4::glmer`是因为H3/H4需要频率学二项GLMM、交叉随机截距、优化器控制和收敛/奇异拟合审计。Python `statsmodels`当前可用的二项混合模型主要采用贝叶斯估计，不作为本研究的等价确认性引擎。

---

## 2. H3方法集合与权重

H3主要边际对比只包含以下四种非Oracle方法：

```text
full_schema
lexical_top5
dense_top5
hierarchical
```

方法权重固定为：

```text
各方法等权
```

不按有效观测数、成功运行数或缺失比例加权。Oracle Boundary、Oracle Top-5及其他Oracle条件不进入H3主要边际平均。

若四种方法中任一种缺失，H3正式模型拒绝运行；不能通过重新归一化剩余方法权重产生主要结论。

---

## 3. H3结构性空单元参数化

预注册控制剂量包含：

```text
none-0
lexical-4
lexical-8
functional_overlap-4
functional_overlap-8
```

由于`none`只在0剂量出现，直接展开`near_neighbor_type × near_neighbor_count`会产生结构性空单元和秩亏。正式实现使用等价的五水平分类变量：

```text
neighbor_condition
```

映射为：

```text
none + 0                    → none_0
lexical + 4                 → lexical_4
lexical + 8                 → lexical_8
functional_overlap + 4      → functional_overlap_4
functional_overlap + 8      → functional_overlap_8
```

该参数化只重写设计矩阵，不增加或删除实验条件。H3主要计划对比仍为：

```text
functional_overlap_8 − lexical_8 < 0
```

H3确认性模型：

```text
selection_correct
~ method
+ neighbor_condition
+ difficulty_score_z
+ (1 | minimal_pair_group)
+ (1 | target_tool_family)
+ (1 | pool_family_id)
+ (1 | model_run_repeat)
```

H3主要模型估计四种方法等权平均后的近邻干扰总效应。它不假设每种方法受到完全相同程度的干扰，也不能据此声称四种方法的条件效应同质。

`schema_token_count`可能处于“路由方法→Schema暴露长度→选择性能”的因果路径上。主要模型不控制`schema_token_count_z`，避免把方法通过减少Schema暴露产生的真实效果调整掉。因此主要结果解释为方法在实际Schema暴露机制下的总效应，而不是固定Schema长度后的直接效应。

预注册两个H3敏感性模型：

```text
Schema调整敏感性：
selection_correct
~ method
+ neighbor_condition
+ difficulty_score_z
+ schema_token_count_z
+ 同主要模型的随机效应

方法异质性敏感性：
selection_correct
~ method × neighbor_condition
+ difficulty_score_z
+ 同主要模型的随机效应
```

方法异质性模型逐方法报告`functional_overlap_8 − lexical_8`，用于判断平均效应是否由单一方法主导。它属于次要敏感性分析，不改变H3主要确认性检验，也不要求每个方法分别显著。

`difficulty_score_z`和敏感性模型中的`schema_token_count_z`使用确认性输入子集的总体均值和总体标准差标准化。标准化参数必须写入模型元数据。

---

## 4. H4模型和支持等级

H4只读取`mixed_realistic`。确认性模型：

```text
selection_correct
~ method
+ log(tool_pool_size)
+ method × log(tool_pool_size)
+ difficulty_score_z
+ (1 | minimal_pair_group)
+ (1 | target_tool_family)
+ (1 | pool_family_id)
+ (1 | model_run_repeat)
```

H4主要模型同样不控制`schema_token_count_z`，估计包含Schema压缩路径在内的方法规模稳定性总效应。预注册敏感性模型在完全相同的固定效应和随机效应结构上加入`schema_token_count_z`，用于报告控制Schema长度后的直接效应。敏感性结果不能替代主要模型，也不能改变主要H4支持等级。

以响应概率尺度上的17→120端点差计算三项差中差：

```text
D_H4_hierarchical − D_H4_full_schema > 0
D_H4_hierarchical − D_H4_lexical_top5 > 0
D_H4_hierarchical − D_H4_dense_top5 > 0
```

三项使用单侧检验，并对原始`p`值进行Holm校正。

报告等级固定为：

- `full_support`：三项估计均大于0，且三项Holm校正后`p < 0.05`；
- `partial_support`：三项方向均大于0，至少一项但并非全部通过Holm门槛；
- `not_supported`：没有任何比较通过，或任一项方向不大于0。

`partial_support`不能表述为“H4成立”。

---

## 5. 优化器与收敛判定

每个模型按以下顺序运行：

1. `bobyqa`，`maxfun=200000`；
2. 若未通过，保持同一模型改用`Nelder_Mead`，`maxfun=200000`。

共同设置：

```text
calc.derivs = TRUE
check.conv.grad tolerance = 2e-3
check.conv.hess tolerance = 1e-6
isSingular tolerance = 1e-4
```

模型通过必须同时满足：

- 没有`lme4`收敛消息；
- 优化器收敛码为0；
- Hessian可用且没有负特征值警告；
- `isSingular(model, tol=1e-4) = FALSE`。

所有尝试均写入`model_attempts.csv`，不能只保留最终成功尝试。

---

## 6. 预注册简化链

本模型没有相关随机斜率，因此“去除相关随机斜率”步骤不适用。

若完整模型奇异，按以下顺序处理：

1. 若`model_run_repeat`随机截距标准差`≤ 1e-4`，删除该随机截距并重新执行两个优化器；
2. 若仍奇异且`pool_family_id`随机截距标准差`≤ 1e-4`，删除该随机截距并重新执行两个优化器；
3. `minimal_pair_group`和`target_tool_family`为保护项，不得自动删除；
4. 仍不收敛、仍奇异或不存在符合阈值的可删除项时，正式模型状态为`failed`。

禁止：

- 删除确认性固定效应；
- 根据固定效应显著性决定简化；
- 删除方差未达到阈值的随机截距；
- H3、H4使用不同的事后简化规则；
- 以普通逻辑回归或配对符号检验替代失败的GLMM。

---

## 7. 输出与状态

正式运行必须生成：

- `h3_direct_contrast.csv`
- `h3_baseline_contrasts.csv`
- `h4_scale_stability_mixed.csv`
- `run_repeat_summary.csv`
- `cluster_bootstrap_summary.csv`
- `missingness_audit.csv`
- `h3_glmm_input.csv`
- `h4_glmm_input.csv`
- `h3_standardization.csv`
- `h4_standardization.csv`
- `h3_glmm_fixed_effects.csv`
- `h3_glmm_random_effects.csv`
- `h3_glmm_planned_contrasts.csv`
- `h3_schema_adjusted_sensitivity_glmm_fixed_effects.csv`
- `h3_schema_adjusted_sensitivity_glmm_random_effects.csv`
- `h3_schema_adjusted_sensitivity_contrasts.csv`
- `h3_method_interaction_sensitivity_glmm_fixed_effects.csv`
- `h3_method_interaction_sensitivity_glmm_random_effects.csv`
- `h3_method_interaction_sensitivity_contrasts.csv`
- `h4_glmm_fixed_effects.csv`
- `h4_glmm_random_effects.csv`
- `h4_glmm_planned_contrasts.csv`
- `h4_schema_adjusted_sensitivity_glmm_fixed_effects.csv`
- `h4_schema_adjusted_sensitivity_glmm_random_effects.csv`
- `h4_schema_adjusted_sensitivity_contrasts.csv`
- `model_status.csv`
- `model_attempts.csv`
- `engine_metadata.csv`
- `confirmatory_report.json`
- `artifact_manifest.csv`

`artifact_manifest.csv`记录除自身外全部正式产物的SHA-256。正式契约共30类文件，必须覆盖GLMM实际输入、标准化参数和5套随机效应。最终报告同时记录输入文件哈希、`r_engine_lock.json`哈希、分析Git提交和已跟踪工作区清洁状态；真实数据正式验收不得省略这些可复现字段。

H3或H4主要模型失败时正式管线失败。敏感性模型失败时允许继续生成主要结果，但必须在`model_status.csv`、模型尝试和报告中明确记录；失败的敏感性模型不能改变主要支持等级。

正式管线无权自行把CF-11改为`passed`，报告始终保持：

```text
cf11_status = in_progress
```

真实候选干跑后，独立`finalize_cf11.py`必须重新验证产物集合与哈希，并读取绑定同一输入、提交和manifest的真实干跑证据、统计审查、报告审查及项目审批。只有该程序生成的独立最终化记录可以把CF-11组件状态记为`passed`；它不修改原始分析报告，也不代表CF-01至CF-10通过。

最终化采用`protected_repository_review`内部审批记录模式，不把普通JSON内容哈希称为密码学数字签名。记录必须包含`reviewer_role`、`organization_or_team`、`review_scope`和带时区的`recorded_at`，并满足：

```text
analysis.generated_at
≤ candidate_evidence.recorded_at
≤ statistics_review/report_review.recorded_at
≤ project_approval.recorded_at
```

统计审查人与项目审批人必须不同。manifest文件名必须是解析后仍位于分析目录内的相对路径；拒绝绝对路径、驱动器路径、`..`和符号链接逃逸。最终化记录只能独占创建，禁止覆盖已有记录，并包含由分析报告、manifest和四份证据哈希导出的确定性`finalization_id`。

证据文件和最终化记录必须通过受保护分支、角色审批和Git签名提交纳入仓库。`finalize_cf11.py`只验证文件内容与流程约束，不验证Git托管平台权限或提交签名本身。

---

## 8. 内容级验收

除文件存在性外，正式管线必须验证：

- H3主要计划对比集合与预注册完全一致；
- H4恰好包含三个预注册方法对比；
- 5个模型均有唯一且明确的`converged`或`failed`状态；
- 主要模型必须收敛，敏感性失败必须显式披露；
- 收敛模型的估计量、双侧95%置信区间和p值均为有限数；
- H4单侧原始p值的Holm校正能够独立复算；
- H3方法异质性结果覆盖全部四种正式方法；
- manifest文件集合与正式契约完全一致且哈希可复算。
