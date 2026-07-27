# Core Frozen CF-11最小实现包

本目录实现`statistical_analysis_interface_v1.0-rc1.1.md`的数据契约、配对构造、描述性聚合、问题组簇级Bootstrap和H4三项Holm校正。

当前实现不包含正式广义线性混合效应模型拟合，因此输出会明确记录：

```text
formal_mixed_effect_model.status = not_run
cf11_status = in_progress
```

不得将最小包的配对符号检验结果替代协议规定的正式混合效应模型。

## 文件

| 文件 | 用途 |
| --- | --- |
| `analysis_schema.json` | 输入JSON Schema |
| `validate_analysis_input.py` | 无第三方依赖的输入与跨字段校验 |
| `build_paired_contrasts.py` | H3/H4原始配对和H4方法间对比 |
| `bootstrap_clusters.py` | 问题组簇级Bootstrap |
| `run_h3_confirmatory.py` | H3最小验证报告 |
| `run_h4_confirmatory.py` | H4最小验证报告及三项Holm校正 |
| `confirmatory_report_template.json` | 正式报告字段模板 |
| `tests/` | 合成数据契约测试 |

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

完整字段与状态约束见`analysis_schema.json`。运行分析前必须先通过输入校验。

## 命令

在项目根目录执行：

```powershell
& '.\.venv\Scripts\python.exe' 'Tools\core_freeze\validate_analysis_input.py' input.json

& '.\.venv\Scripts\python.exe' 'Tools\core_freeze\run_h3_confirmatory.py' input.json `
  --output h3_report.json

& '.\.venv\Scripts\python.exe' 'Tools\core_freeze\run_h4_confirmatory.py' input.json `
  --output h4_report.json

& '.\.venv\Scripts\python.exe' -m unittest discover `
  -s 'Tools\core_freeze\tests' -t . -v
```

正式分析默认要求每个任务和运行重复都具有A—E五个工具池重复。`--allow-incomplete`只能用于开发诊断，不能用于正式确认性报告。

## CF-11剩余门槛

- 选择并冻结正式混合效应模型引擎和版本；
- 实现H3、H4两套GLMM及收敛/简化审计；
- 按接口生成全部正式CSV结果文件；
- 完成真实候选数据的输入校验和试运行；
- 形成统计审查记录、报告模板审查记录和审批签署。
