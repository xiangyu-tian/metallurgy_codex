# verified_core v1

本目录保存首批可用于确认性实验的工具合同与独立参考验证。

## 当前范围

| 工具 | 可确认性使用的范围 |
| --- | --- |
| A001 | 合同列出的 8 组单位对；严格量纲检查；线性和仿射换算 |
| A002 | `neutral_formula_grammar_v1` 中性化学式语法 |
| A003 | 合同列出的 8 种元素及 A002 语法范围内的摩尔质量 |
| A004 | 非负、有限且总和大于 0 的共同标度权重向量 |
| B019 | 显式声明 `fraction` 或 `percent` 的二元两相杠杆规则 |

`verified_core`不是对工具名称或全部潜在输入域的笼统背书，只对
`contracts_v1.json`中的`verification_scope`成立。实现能接受但合同未覆盖的输入，
不得进入E1b确认性`Forced Verified Tool`数据。

## 文件

- `tool_contract.schema.json`：工具合同结构；
- `contracts_v1.json`：五个版本化合同及其规范化SHA-256；
- `reference_cases_v1.json`：独立冻结的正常、边界、量纲和变形案例；
- `validate_verified_core.py`：合同、版本、覆盖和参考结果验证器。

期望值直接冻结在参考案例文件中，验证器不会调用生产实现来生成期望答案。
生产工具只作为被测对象运行。

## 运行

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\verified_core\validate_verified_core.py' `
  --output-dir 'outputs\verified_core_v1_20260730'
```

成功门槛：

1. 五个合同哈希和运行时工具版本一致；
2. 每个工具至少有正常案例和边界案例；
3. 所有独立参考案例通过；
4. 失败案例返回预期的标准错误代码。

## 仍然不由本验证解决的问题

- 自然语言问题是否正确表达了真实冶金状态；
- 相图端点、真实工况或材料数据是否正确；
- 合同范围外输入是否可靠；
- 其他12个当前工具以及120工具目录是否已验证；
- Core Frozen治理清单是否整体完成。

B019只验证给定端点后的代数计算。输入是否来自同一温度、压力和等温连线，
必须由后续任务数据来源或外部基准保证。
