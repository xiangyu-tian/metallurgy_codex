# CF-05 E3 B019 运行时隐式组元修复与验证 v1

日期：2026-08-11
状态：开发性修复验证通过；`CF-05=in_progress`；`Core Frozen=false`

## 目的

上一阶段的严格参数门控可以从候选参数中移除请求未提供的 `component`，但 B019 运行时仍会通过 `params.get("component", "B")` 静默补入组元 B。这样会把“请求没有证据”改写成“工具假定为 B”，不符合参数可追溯要求。

本轮只修复这一运行时语义，不改变杠杆规则公式、不修改正式工具目录，也不进行确认性推断。

## 修复

- B019 输入 Schema 不再为可选参数 `component` 声明默认值；
- 省略 `component` 时，输出为 `null`，并记录 `component_grounding_status=unspecified`；
- 显式提供 `component` 时原样保留，并记录 `component_grounding_status=explicit`；
- `composition_basis=auto` 仍保留为旧调用兼容面，但冻结的正式 Schema 和严格参数门控仍只接受显式 `fraction` 或 `percent`。

`component` 不是杠杆规则数值计算的输入变量，因此本次修复不改变相分数与守恒残差。

## 冻结回放结果

输入绑定到上一阶段冻结的 16 个 B019 严格门控候选参数：

| 指标 | 结果 |
| --- | ---: |
| 冻结回放单元 | 16 |
| 成功并通过数值与组元语义校验 | 16 |
| 运行时隐式输出 `component=B` | 0 |
| 正确输出 `component=null, status=unspecified` | 16 |
| 边界用例 | 4/4 通过 |
| 本地确定性工具调用 | 20 |
| 外部 API 调用 | 0 |

边界用例覆盖：省略组元、显式组元、百分数标度和总体成分越出两相端点。

## 测试结果

本轮聚焦测试共 10 项：

- 7 项新增运行时修复与产物审计测试；
- 3 项既有 B019 数值与边界回归测试；
- 10/10 通过。

附加运行整个 `VerifiedCoreRegressionTests` 时，B019 项全部通过，但发现既有 A001 用例仍存在一项无关失败：未知单位实际返回 `UNIT_MISMATCH`，测试期待 `INVALID_INPUT`。该问题未由本次 B019 变更引入，也没有在本轮越界修改。

## 证据

- 配置：`Tools/core_freeze/e3_routing/b019_runtime_remediation_validation_config_v1.json`
- 验证器：`Tools/core_freeze/e3_routing/validate_b019_runtime_remediation.py`
- 测试：`Tools/core_freeze/tests/test_v11_cf05_e3_b019_runtime_remediation.py`
- 产物：`outputs/v11_cf05_e3_b019_runtime_remediation_v1_20260811/`

产物目录包含配置快照、16 单元逐条回放、边界结果、汇总报告和 SHA-256 清单。

## 结论与下一步

运行时隐式组元风险已经在开发候选实现中关闭，上一阶段 16 个候选参数现在具备本地确定性执行条件。该结果只说明 B019 参数证据链和本地计算兼容面通过验证，不能升级 `CF-05` 或 `Core Frozen` 状态。

下一步回到 E3 原定主线：将同一“严格参数门控 + 无隐式默认值”约束扩展到其余 verified-core 工具的参数面，然后再扩大目标工具和任务覆盖；不访问独立验证集，不进行新的外部 API 调用，除非形成冻结开启包并获得单独授权。
