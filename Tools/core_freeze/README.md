# Core Frozen CF-11统计实现包

本目录实现`statistical_analysis_interface_v1.0-rc1.1.md`的数据契约、配对构造、描述性聚合、问题组簇级Bootstrap、H3/H4正式广义线性混合效应模型（GLMM）和正式结果文件输出。

正式模型的引擎、版本、优化器、收敛阈值和简化链已冻结在：

- `r_engine_lock.json`
- `docs/experiments/glmm_engine_spec_v1.0-rc1.md`

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
| `confirmatory_report_template.json` | 确认性报告字段模板 |
| `tests/` | 合成数据契约和GLMM集成测试 |

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

运行测试：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover `
  -s 'Tools\core_freeze\tests' -t . -v
```

正式分析默认要求每个任务和模型运行重复都具有A—E五个工具池重复。描述性脚本的`--allow-incomplete`只能用于开发诊断，不能用于正式确认性报告。

## CF-11剩余门槛

- 用真实`rc1.1`候选数据完成输入校验和正式管线干跑；
- 形成统计审查记录和报告模板审查记录；
- 完成统计审查人与项目负责人的审批签署。
