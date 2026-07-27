# H3/H4 GLMM引擎实现规范 v1.0-rc1

## 文档状态

- 版本：`1.0-rc1`
- 日期：2026-07-27
- 上位统计接口：`statistical_analysis_interface_v1.0-rc1.1.md`
- 状态：正式实现候选版；待真实候选数据干跑和统计审查

本文冻结统计引擎、模型参数化、方法权重、收敛判定、简化链和H4支持等级。本文不改变H1—H4或工具池设计。

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
+ schema_token_count_z
+ (1 | minimal_pair_group)
+ (1 | target_tool_family)
+ (1 | pool_family_id)
+ (1 | model_run_repeat)
```

`difficulty_score_z`和`schema_token_count_z`使用确认性输入子集的总体均值和总体标准差标准化。标准化参数必须写入模型元数据。

---

## 4. H4模型和支持等级

H4只读取`mixed_realistic`。确认性模型：

```text
selection_correct
~ method
+ log(tool_pool_size)
+ method × log(tool_pool_size)
+ difficulty_score_z
+ schema_token_count_z
+ (1 | minimal_pair_group)
+ (1 | target_tool_family)
+ (1 | pool_family_id)
+ (1 | model_run_repeat)
```

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
- `h3_glmm_fixed_effects.csv`
- `h3_glmm_planned_contrasts.csv`
- `h4_glmm_fixed_effects.csv`
- `h4_glmm_planned_contrasts.csv`
- `model_attempts.csv`
- `engine_metadata.csv`
- `confirmatory_report.json`

只要任一正式GLMM为`not_run`或`failed`，报告必须保持：

```text
cf11_status = in_progress
```

CF-11只有在真实候选数据干跑、全部输出验收和正式审批完成后才能申请`passed`。

