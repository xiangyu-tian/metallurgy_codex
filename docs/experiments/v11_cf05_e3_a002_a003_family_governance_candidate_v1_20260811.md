# CF-05 E3 A002/A003 工具家族治理候选 v1

日期：2026-08-11

状态：候选规则已生成并通过自动验证；等待项目级采用；`CF-05=in_progress`；`Core Frozen=false`

## 1. 推荐治理方案

采用“保留两个端点、按一个能力家族治理”的方案：

```text
family_id = CHEMICAL_FORMULA_ANALYSIS-V1
members = [A002, A003]
relation = asymmetric_output_overlap
```

角色定义：

- A002：元素计量解析的功能较宽端点，同时输出摩尔质量和质量分数；
- A003：专用摩尔质量视图，显式输出数值和`g/mol`单位。

本候选不删除端点、不修改运行时、不覆盖正式目录和金标。

## 2. 为什么必须同时保留两种计数

### 可调用端点数

```text
A002 + A003 = 2 endpoints
```

用于衡量模型实际面对的：

- Schema数量；
- 上下文长度；
- 路由候选数量；
- API函数暴露负载。

因此，H4的17/50/100/120主尺度仍使用：

```text
endpoint_schema_count
```

### 家族去重能力数

```text
A002 + A003 = 1 family-deduplicated capability
```

用于约束对外表述中的“独立科学能力数量”。如果只报告120个端点，却称为120个完全独立专业能力，会受到A002/A003这种重叠关系影响。

H4同时附带报告：

```text
family_deduplicated_capability_count
```

该伴随指标不替换预注册的H4主尺度。

## 3. 四层计分

冻结主要指标仍为：

```text
primary_acceptable_tool_selection_accuracy
```

同时独立报告：

1. `tool_family_selection_accuracy`；
2. `alternative_success_rate`；
3. `scientific_success_including_alternatives`。

次要指标不能改变主要假设的支持等级。

### 典型判定

| 任务 | 选择 | 主要命中 | 家族命中 | Alternative Success | 科学成功 |
| --- | --- | ---: | ---: | ---: | ---: |
| A003摩尔质量 | A003 | 1 | 1 | 0 | 1 |
| A003摩尔质量 | A002 | 0 | 1 | 1 | 1 |
| A002元素解析 | A002 | 1 | 1 | 0 | 1 |
| A002元素解析 | A003 | 0 | 1 | 0 | 0 |
| A003摩尔质量 | 无关工具 | 0 | 0 | 0 | 0 |

这张表说明：家族命中不等于科学成功。由于重叠方向不对称，A003不能替代A002的元素计量输出。

## 4. H3使用边界

A002/A003不能进入H3的对称功能近邻确认性金标：

```text
eligible_as_symmetric_functional_neighbor_pair = false
```

允许的用途是：

```text
asymmetric_overlap_secondary_analysis
```

即研究模型是否偏好专用端点、是否选择功能较宽端点，以及这种选择是“端点偏好错误”还是“科学失败”。

## 5. 对既有A003结果的影响

对已完成的96个A003开发单元进行离线重分类：

| 指标 | 数量 |
| --- | ---: |
| 主要成功 | 96/96 |
| 家族命中 | 96/96 |
| Alternative Success | 0/96 |
| 含替代的科学成功 | 96/96 |

原因是既有96个单元全部选择A003。因此治理候选不会追溯改变已报告的主要准确率，只规范未来遇到A002选择时如何分类。

## 6. 自动验证

- 家族治理测试：8项；
- 上一阶段重叠审计回归：8项；
- 合计：16/16通过；
- 外部API调用：0；
- 新增工具执行：0；
- 正式目录、正式金标和研究协议均未修改。

证据：

- `Tools/core_freeze/e3_routing/a002_a003_family_governance_config_v1.json`
- `Tools/core_freeze/e3_routing/build_a002_a003_family_governance.py`
- `Tools/core_freeze/tests/test_v11_cf05_e3_a002_a003_family_governance.py`
- `outputs/v11_cf05_e3_a002_a003_family_governance_v1_20260811/`

## 7. 下一步

项目级采用该候选后，构造两类最小差异任务：

1. A002元素计量任务：A002主要可接受，A003不构成科学成功；
2. A003摩尔质量任务：任务级冻结主要集合，A002作为Alternative Success。

任务包必须同时提供主要、家族、替代和科学成功四类预期标签，并明确该任务对只用于非对称重叠的次要分析，不进入H3对称近邻确认性比较。
