# CF-05 E3 A001/A002 参数证据审计与严格门控 v1

日期：2026-08-11

状态：开发性联合审计与离线门控回放通过；`CF-05=in_progress`；`Core Frozen=false`

## 目的

在 B019 的隐式可选参数风险关闭后，本轮检查 verified-core 中的：

- A001：单位换算；
- A002：中性化学式解析。

检查重点不是重复计算答案，而是确认模型生成的工具参数是否直接来自请求、是否包含未知字段，以及请求是否位于冻结合同的能力边界内。

## 数据范围

现有多目标开发结果包含：

| 工具 | 唯一任务 | 单元 | 方法 | 工具规模 |
| --- | ---: | ---: | --- | --- |
| A001 | 2 | 16 | Full Schema、Lexical Top-5、Dense Top-5、Hierarchical | 17、120 |
| A002 | 2 | 16 | Full Schema、Lexical Top-5、Dense Top-5、Hierarchical | 17、120 |

因此，32个单元可验证跨方法和规模的实现一致性，但只来自4个唯一任务，不能被解释为广泛任务分布上的性能证据。

## 审计结果

- 32/32 单元的必需参数完整；
- 32/32 单元的参数与请求证据逐项一致；
- 未发现未知参数、未依据请求改写参数或隐式可选参数；
- A001/A002 运行时均不需要像 B019 那样修复默认值；
- 当前源 Schema 的必需字段与 verified contract 一致，但没有显式设置 `additionalProperties=false`。

正式 Schema 候选因此只做两项收紧：

1. 设置 `additionalProperties=false`；
2. 明确参数必须与请求证据一致，并由合同门控判断能力范围。

没有修改正式目录。

## 双层严格门控

### A001

第一层从请求中确定性抽取：

```text
value + source_unit + target_unit
```

第二层检查：

- 三项参数是否完整；
- 数值和换算方向是否与请求完全一致；
- 是否出现额外参数；
- 有向单位对是否位于 verified contract 的冻结范围。

例如 `kg → lb` 即使运行时代码可能支持，也不属于当前确认性合同范围，因此进入 `review_required`，不能自行扩大能力声明。

### A002

第一层从请求中抽取显式中性化学式；第二层检查：

- `formula` 是否完整且逐字符一致；
- 是否出现额外参数；
- 是否通过冻结的完整词法消费、括号配对、正计量数和已知元素规则。

`Fe2O3abc` 等不完整语法进入 `review_required`。

## 挑战结果

16/16 个挑战用例通过，覆盖：

- 正常单位换算和嵌套化学式；
- 请求—参数不一致；
- 缺失必需参数；
- 未知参数；
- 超出 verified contract；
- 错选工具；
- 请求不可确定解析。

决策阶段不读取任务金标；金标仅在决策完成后用于离线核对现有32个单元。

## 测试与证据

- 新增门控及产物测试：8项；
- 相关既有 A001/A002 回归：5项；
- 合计：13/13通过；
- 外部 API 调用：0；
- 工具执行：0。

主要文件：

- `Tools/core_freeze/e3_routing/a001_a002_strict_parameter_gate.py`
- `Tools/core_freeze/e3_routing/a001_a002_strict_parameter_gate_config_v1.json`
- `Tools/core_freeze/e3_routing/a001_a002_strict_parameter_gate_challenge_v1.json`
- `Tools/core_freeze/tests/test_v11_cf05_e3_a001_a002_strict_parameter_gate.py`
- `outputs/v11_cf05_e3_a001_a002_strict_parameter_gate_v1_20260811/`

## 结论与下一步

A001/A002 的现有参数生成没有发现证据忠实度缺陷，当前需要的是正式调用边界收紧，不是运行时修复。

下一步应转向 A003。A003 与 A002 接收相同的化学式输入，但 A002 的正式合同和运行结果本身也包含 `molar_mass`。因此，不能预先把二者当成对称且相互排斥的近邻；下一阶段先复核 A002 对既有 A003 任务的直接满足和 Alternative Success，再决定任务对及独立工具计数方式。
