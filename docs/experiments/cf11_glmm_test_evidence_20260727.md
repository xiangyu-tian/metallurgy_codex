# CF-11正式GLMM实现与测试证据

## 记录状态

- 日期：2026-07-27
- 统计接口：`1.0-rc1.1`
- GLMM规范：`1.0-rc1`
- 协议：`1.0-rc3.1`
- 数据规范：`1.0-rc3`
- 结论：正式GLMM引擎和输出契约已在合成数据上通过；CF-11继续保持`in_progress`

---

## 1. 冻结环境

项目内安装了隔离运行时，不修改系统PATH：

```text
R 4.6.1
lme4 2.0.6
emmeans 2.0.4
```

全部直接和间接R依赖的精确版本记录在：

```text
Tools/core_freeze/r_engine_lock.json
```

引擎检查会比较R和每个包的实际版本；不一致时拒绝运行正式分析。

---

## 2. 已实现的确认性分析

H3：

- 固定四种非Oracle方法并等权汇总；
- 使用五级`neighbor_condition`避免结构性空单元；
- 主要直接对比为`functional_overlap-8`与`lexical-8`；
- `none-0`作为共同基准；
- 输出固定效应、随机效应、计划对比、收敛尝试和标准化参数。

H4：

- 只使用`mixed_realistic`工具池；
- 用`method × log(tool_pool_size)`拟合规模变化；
- 在响应概率尺度计算17到120工具的端点下降差；
- 对三项层次化方法优势做单侧检验和Holm校正；
- 输出`full_support / partial_support / not_supported`。

两套模型均使用`binomial(link="logit")`、Laplace近似和`nAGQ=1`。优化器、阈值、随机效应简化链以及受保护随机效应见`glmm_engine_spec_v1.0-rc1.md`。

---

## 3. 正式产物契约

`formal_pipeline.py`一次运行至少生成：

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

同时保留GLMM原始输入、随机效应方差和协变量标准化参数，便于复核。

---

## 4. 合成数据集成测试

执行：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest `
  'Tools.core_freeze.tests.test_glmm_engine' -v
```

结果：

```text
Ran 2 tests in 24.519s
OK
```

测试覆盖：

- R及所有包版本锁校验；
- H3/H4交叉效应合成数据导出；
- H3/H4正式GLMM拟合和收敛；
- H3等权方法计划对比；
- H4三项Holm校正与支持等级；
- 正式CSV/JSON产物全集存在性；
- 报告仍保持`cf11_status=in_progress`。

完整Core Freeze测试集结果：

```text
Ran 15 tests in 25.249s
OK
```

既有离线回归结果：

```text
Ran 44 tests
OK
Golden benchmark: 138 cases, 17 models, baseline 2.0.0
```

---

## 5. 真实候选数据准备度

仓库现有`Tools/benchmarks/results/`结果来自M4.5/M4.6工程实验，数据版本和字段结构早于统计接口`1.0-rc1.1`。这些文件没有完整的：

- H3五级近邻条件与A—E工具池重复；
- H4的17/50/100/120现实混合池嵌套结果；
- 固定四方法的等权配对设计；
- `difficulty_score`和`schema_token_count`；
- 问题组、目标工具族、工具池族和模型运行重复交叉标识。

因此不能将既有结果转换后冒充正式候选数据，也不能据此宣布完成真实数据干跑。真实干跑必须等待CF-01/CF-02形成并冻结候选任务、工具池和运行数据。

---

## 6. 冻结判断

已关闭：

- 正式引擎与版本选择；
- H3/H4 GLMM实现；
- 收敛和简化审计；
- 正式CSV/JSON输出全集；
- 合成数据端到端集成测试。

仍开放：

- 真实候选数据输入校验与正式管线干跑；
- 统计审查和报告模板审查；
- 审批签署。

因此：

```text
CF-11 = in_progress
Core Frozen = false
```
