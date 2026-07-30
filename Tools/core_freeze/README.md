# Core Frozen CF-11统计实现包

> 研究主线已升级到`research_protocol_v1.1-rc1`。首批无需专家逐题标注的
> 可执行工具合同与独立参考验证位于`verified_core/`；本目录其余CF-11文件仍是
> 历史`v1.0-rc3.1`统计实现，不能单独证明新版Core Frozen完成。

本目录实现`statistical_analysis_interface_v1.0-rc1.1.md`的数据契约、配对构造、描述性聚合、问题组簇级Bootstrap、H3/H4正式广义线性混合效应模型（GLMM）和正式结果文件输出。

正式模型的引擎、版本、优化器、收敛阈值和简化链已冻结在：

- `r_engine_lock.json`
- `docs/experiments/glmm_engine_spec_v1.0-rc1.1.md`

当前实现已通过合成交叉效应数据测试，但真实`rc1.1`候选数据尚未形成，统计审查与项目审批也未完成。因此正式报告仍必须记录：

```text
cf11_status = in_progress
```

合成数据测试只能验证实现和输出契约，不能替代真实候选数据干跑或审批。

## 文件

| 文件 | 用途 |
| --- | --- |
| `analysis_schema.json` | 输入JSON Schema |
| `validate_analysis_input.py` | 输入与跨字段校验 |
| `build_paired_contrasts.py` | H3/H4原始配对和H4方法间对比 |
| `bootstrap_clusters.py` | 问题组簇级Bootstrap |
| `run_h3_confirmatory.py` | H3描述性与最小验证报告 |
| `run_h4_confirmatory.py` | H4描述性与最小验证报告 |
| `r_engine_lock.json` | R及统计包精确版本和模型配置锁 |
| `glmm_engine.R` | H3/H4正式GLMM、计划对比及收敛审计 |
| `r_engine.py` | Python到冻结R引擎的输入导出与调用层 |
| `formal_pipeline.py` | 正式CSV/JSON结果全集的一次性生成入口 |
| `finalize_cf11.py` | 校验不可变产物与受治理审批记录并生成独立CF-11最终化记录 |
| `finalization_evidence_template.json` | 真实干跑、统计审查、报告审查和项目审批证据模板 |
| `confirmatory_report_template.json` | 确认性报告字段模板 |
| `prepare_cf01_cf02_pilot.py` | 从现有120例和17工具快照生成CF-01/CF-02首轮准备包 |
| `validate_cf01_cf02_pilot.py` | 校验准备态、双人标注一致性和Track B完整工具池 |
| `pilot_v1/` | 冻结的20例Track A、20任务Track B及隔离模板 |
| `tests/` | 合成数据契约和GLMM集成测试 |

主要确认性模型估计包含Schema暴露机制在内的方法总效应，不控制可能作为中介变量的`schema_token_count_z`。正式管线同时生成Schema调整敏感性模型；H3还生成`method × neighbor_condition`方法异质性敏感性模型。敏感性结果不改变主要H3检验或H4支持等级。

正式契约包含30类文件。GLMM实际输入、标准化参数、5套随机效应和模型状态均进入`artifact_manifest.csv`；最终报告记录输入哈希、R锁文件哈希、分析Git提交和已跟踪工作区清洁状态。

管线会进行内容级验收：计划对比集合、有限估计量与双侧95%置信区间、单侧p值、H4 Holm复算、模型状态和manifest文件集合必须一致。敏感性模型允许明确记录为`failed`，但不得改变主要支持等级；H3或H4主要模型失败时正式管线直接失败。

## 隔离运行环境

本项目使用项目内隔离R运行时，不修改系统PATH：

```text
.r-runtime/R-4.6.1
.r-runtime/library
```

`.r-runtime/`已加入`.gitignore`。正式引擎检查会拒绝与`r_engine_lock.json`不一致的R或包版本。

检查命令：

```powershell
$env:R_LIBS_USER = (Resolve-Path '.\.r-runtime\library').Path
& '.\.r-runtime\R-4.6.1\bin\Rscript.exe' `
  'Tools\core_freeze\glmm_engine.R' --check
```

也可以设置`METALLURGY_RSCRIPT`和`METALLURGY_R_LIBRARY`指向另一套完全匹配锁文件的隔离环境。

## 输入格式

输入文件顶层结构：

```json
{
  "schema_version": "1.0-rc1.1",
  "metadata": {
    "dataset_version": "candidate",
    "protocol_version": "1.0-rc3.1",
    "generated_at": "2026-07-27T00:00:00+08:00"
  },
  "records": []
}
```

完整字段与状态约束见`analysis_schema.json`。正式GLMM还要求每条可观测选择结果包含：

- `difficulty_score`
- `schema_token_count`
- H3或H4对应的任务、工具池、方法和重复字段

## 命令

在项目根目录执行输入校验：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\validate_analysis_input.py' input.json
```

生成正式结果全集：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\formal_pipeline.py' input.json `
  --output-dir output\cf11 `
  --n-resamples 2000 `
  --seed 20260727
```

真实候选干跑完成后，统计脚本本身仍不能把CF-11改为`passed`。填写四份独立证据后执行：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\finalize_cf11.py' output\cf11 `
  --candidate-evidence evidence\candidate_dry_run.json `
  --statistics-review evidence\statistics_review.json `
  --report-review evidence\report_review.json `
  --approval evidence\project_approval.json `
  --output evidence\cf11_finalization_record.json
```

最终化程序重新校验全部产物哈希，并要求四份记录绑定相同的输入哈希、分析提交和manifest哈希。每份记录必须包含角色、团队、审查范围和带时区的`recorded_at`，且满足：

```text
分析生成
≤ 真实候选干跑记录
≤ 统计审查/报告审查记录
≤ 项目审批记录
```

统计审查人不得同时作为项目审批人。manifest只允许解析后仍位于分析目录内的相对路径；绝对路径、`..`和符号链接逃逸都会被拒绝。

最终化记录使用独占创建，已有输出不会被覆盖，并包含确定性的`finalization_id`。它只生成独立记录，不修改原始分析报告。即使CF-11通过，也不代表CF-01至CF-10已经通过。

当前采用`protected_repository_review`内部审批模式。这些JSON是审批记录而非密码学数字签名；内容哈希只能验证一致性，不能证明人员身份。证据和最终化记录必须通过受保护分支、角色权限和Git签名提交纳入仓库。脚本不声称验证了Git托管平台权限或提交签名。

运行测试：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover `
  -s 'Tools\core_freeze\tests' -t . -v
```

生成并校验CF-01/CF-02首轮准备包：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\prepare_cf01_cf02_pilot.py'

& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\validate_cf01_cf02_pilot.py' `
  'Tools\core_freeze\pilot_v1' `
  --stage prepared
```

准备态通过只表示样本清单、字段隔离和构造契约可执行，不表示人工标注、工具池构造或CF-01/CF-02验收已经通过。具体交接规则见`pilot_v1/README.md`。

正式分析默认要求每个任务和模型运行重复都具有A—E五个工具池重复。描述性脚本的`--allow-incomplete`只能用于开发诊断，不能用于正式确认性报告。

## CF-11剩余门槛

- 用真实`rc1.1`候选数据完成输入校验和正式管线干跑；
- 形成统计审查记录和报告模板审查记录；
- 完成统计审查、报告审查和项目负责人的受治理审批记录。
