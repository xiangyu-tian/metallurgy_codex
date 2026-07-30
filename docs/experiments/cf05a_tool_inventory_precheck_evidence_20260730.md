# CF-05A 120工具清单独立性与实现状态预审证据

## 1. 状态

```yaml
audit_id: CF05A-20260730
cf05_status: in_progress
formal_accepted_tool_count: 0
core_frozen: false
```

本轮完成的是AI辅助的工程与独立性预审，不是CF-05要求的计算机与冶金方向联合审核。预审结果不得直接用于把任何工具标记为`count_status=accepted`。

## 2. 输入与证据边界

- 规划清单：`绿色低碳冶金_数据库资料源与120小模型清单.xlsx`
- 读取工作表：`02_小模型清单120`
- 输入文件SHA-256：`7cc30fce08dc93125f265cf22d15da3f99200d9128198d1fb68e0f489cc207ab`
- 当前实现证据：`Tools/models_core/models_a.py`、`models_b.py`、`models_c.py`
- 正常回归与输入鲁棒性前置证据：`Tools/tests/test_model_baseline.py`

废弃或仍在前端展示的页面不作为工具存在性证据。工具实现状态只依据可注册代码入口；正式可用性还必须结合测试、专业适用域审核和CF-05审批。

## 3. 预审结果

| 指标 | 结果 |
| --- | ---: |
| 规划条目 | 120 |
| 唯一模型ID | 120 |
| 唯一规划API函数名 | 120 |
| 代码已实现并具有基线回归/输入鲁棒性证据 | 17 |
| 仅规划、尚未实现 | 103 |
| 初步未发现五字段签名重叠 | 95 |
| 需要家族复审 | 25 |
| 家族复审组数 | 9 |
| 名称完全重复 | 0 |
| 规划API函数名完全重复 | 0 |
| 需要冻结命名映射的已实现工具 | 17 |
| CF-05正式接受 | 0 |

“需要家族复审”表示同场景条目具有相同的类型、核心方法、主要输入和主要输出，不代表已经判定为重复。需要进一步比较输出Schema、适用域、实现依赖和失败模式，决定保留为独立工具、合并为同一工具的不同operation，或拒绝部分条目。

## 4. 命名契约发现

当前17个实现项存在三个命名表面：

1. 规划清单API函数名，例如`convert_units`；
2. `BaseModelTool`内部自动生成的`api_name`，例如`model_a001`；
3. LLM函数Schema实际暴露的名称，例如`A001`。

现状不妨碍17项基线运行，但在构造50/100/120 Full Schema、路由日志和论文复现产物前，必须形成唯一、冻结的一一映射。

## 5. 产物与验证

- 审核工作簿：`outputs/cf05a_tool_inventory_20260730/cf05a_tool_inventory_audit.xlsx`
- 机器可读预审：`outputs/cf05a_tool_inventory_20260730/cf05a_tool_inventory_precheck.json`
- 差距报告：`outputs/cf05a_tool_inventory_20260730/cf05a_gap_report.md`
- 自动校验：`outputs/cf05a_tool_inventory_20260730/cf05a_validation.json`

自动校验结果为`passed`，确认：

- 源条目数和唯一ID/API计数均为120；
- 实现数为17、未实现数为103；
- 预审没有产生正式接受项；
- 9个复审家族共包含25项。

产物哈希：

```text
cf05a_tool_inventory_audit.xlsx
138fc6346c04be13f8014640c949dc466581d028ec04c904d74f054ebff221fc

cf05a_tool_inventory_precheck.json
015fd749ce08dafe913b3b3c822e9b120c4c8d92d75f7910b38670a68ee2ca60
```

## 6. 下一门槛

1. 对当前17项逐项完成专业适用域、输入输出、正常/边界证据和命名映射复审；
2. 对9个家族中的25项完成拆分/合并/拒绝判断；
3. 17项形成正式可接受候选后，再执行CF-02的17工具试构造；
4. 50/100/120工具池只能使用新增实现且通过CF-05审核的工具，不能用规划条目或页面数量补足。

