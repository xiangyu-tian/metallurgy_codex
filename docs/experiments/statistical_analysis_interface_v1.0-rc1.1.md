# H3/H4 统计分析实现接口 v1.0-rc1.1

## 文档状态

- 版本：`1.0-rc1.1`
- 日期：2026-07-27
- 状态：实现规范候选版；用于先导实验和正式统计脚本
- 上位协议：`research_protocol_v1.0.md`（`1.0-rc3.1`）
- 数据规范：`dataset_v2_annotation_policy_v1.0.md`（`1.0-rc3`）

本文只固定 H3、H4 的确认性对比、配对单位和汇总顺序，不改变研究问题、假设、数据标签或工具池设计。正式实验前，统计脚本、数据表和报告模板必须共同遵守本文。

---

## 1. 分析对象与标识

统计脚本使用由任务金标准、工具池元数据和实验运行结果连接得到的分析视图。该视图至少包含以下字段；“派生”字段不回写任务金标准：

| 字段 | 含义 |
| --- | --- |
| `task_id` | 任务唯一标识 |
| `minimal_pair_group` | 最小差异问题组；不属于问题组时使用稳定的单任务簇标识 |
| `target_tool_family` | 目标工具家族 |
| `method` | 被比较的路由或选择方法 |
| `tool_pool_size` | 工具池规模：17、50、100或120 |
| `pool_design` | `controlled_dose`、`pure_type_exploratory`或`mixed_realistic` |
| `near_neighbor_type` | `none`、`lexical`或`functional_overlap` |
| `near_neighbor_count` | 0、4或8 |
| `pool_family_id` | 同一目标任务、同一无关干扰基底下可配对的工具池家族 |
| `pool_repeat` | 工具池重复，固定为A—E |
| `model_run_repeat` | 同一条件下的模型运行重复 |
| `selection_correct` | 派生字段；`selected_tool ∈ acceptable_tools`时为1，否则为0 |
| `end_to_end_correct` | 派生字段；是否完成正确端到端结果，取0或1 |
| `request_status` | 请求状态：`accepted`或`not_accepted` |
| `execution_status` | 执行状态：`success`、`model_failure`、`provider_failure`、`timeout`或`invalid_response`；请求未被接受时为`null` |

`pool_repeat`由预注册的A—E种子表映射得到。`pool_family_id`必须保证比较条件除预先规定的工具规模、近邻类型或近邻数量外，其余构造因素一致。不能仅凭事后名称相似将不成对的工具池视为配对样本。

---

## 2. H3主要确认性对比

### 2.1 固定条件

H3主要分析固定为：

```text
tool_pool_size = 120
pool_design = controlled_dose
near_neighbor_count = 8
```

在同一：

```text
task_id
× pool_family_id
× pool_repeat
× model_run_repeat
× method
```

内配对比较：

```text
functional_overlap, 8
vs lexical, 8
```

`none, 0`作为共同基准，用于解释两类干扰相对于无近邻条件的损失，不替代上述直接对比。

### 2.2 效应量

主要效应定义为：

```text
D_H3
= Accuracy(functional_overlap, 8)
− Accuracy(lexical, 8)
```

辅助效应定义为：

```text
Effect_functional
= Accuracy(functional_overlap, 8)
− Accuracy(none, 0)

Effect_lexical
= Accuracy(lexical, 8)
− Accuracy(none, 0)
```

方向性假设为：

```text
D_H3 < 0
```

即功能重叠近邻造成的准确率损失大于词法近邻。

### 2.3 检验与报告

- 主要推断使用预注册混合效应模型在120工具、8近邻条件下导出的`functional_overlap − lexical`计划对比；任务、工具池和模型重复保持配对，采用单侧检验，显著性水平为`α = 0.05`；
- 同时报告`D_H3`的原始配对点估计、双侧95%问题组簇级Bootstrap置信区间，以及混合效应模型计划对比的单侧`p`值；
- 报告`Effect_functional`与`Effect_lexical`及其双侧95%置信区间；
- 主文中的方向性结论以预注册的直接对比为准，不能以两个辅助效应分别显著与否代替；
- `selection_correct`为主要工具选择指标，`end_to_end_correct`作为端到端辅助指标，二者不得混合计算。

---

## 3. H4主要确认性对比

### 3.1 固定条件

H4只在以下工具池中计算主要效应：

```text
pool_design = mixed_realistic
```

对每个`method`，在同一：

```text
task_id
× pool_family_id
× pool_repeat
× model_run_repeat
```

内配对比较17工具与120工具。

### 3.2 效应量

```text
D_H4_method,mixed
= Accuracy(method, 120, mixed_realistic)
− Accuracy(method, 17, mixed_realistic)
```

`D_H4`越接近0，表示方法的规模稳定性越好。比较方法间稳定性时，报告各方法`D_H4`的直接差值及双侧95%问题组簇级Bootstrap置信区间；正式推断使用预注册混合效应模型中的`method × log(tool_pool_size)`交互项。

以下结果不替代H4主要结果：

- `controlled_dose`：用于解释规模和近邻剂量机制；
- `pure_type_exploratory`：只作探索性分析；
- 50、100工具条件：用于趋势展示或模型拟合。

---

## 4. 固定汇总顺序

H3与H4必须维护两条互相独立的数据流。

### 4.1 描述性效应与Bootstrap

1. **形成原始配对。** 在`task_id × pool_family_id × pool_repeat × model_run_repeat`内形成条件差值，任何聚合都不得先于配对。
2. **汇总工具池重复。** 对同一`task_id × model_run_repeat`的A—E五个工具池重复取算术平均；同时保留每个池的原始结果。
3. **汇总模型运行重复。** 分别计算每个`model_run_repeat`的全测试集指标，再对重复运行报告均值和标准差；主要分析不使用多数投票。
4. **计算不确定性。** 以预先定义的问题组为最小抽样簇进行Bootstrap；同一簇内的所有任务、A—E工具池和模型重复必须整体保留。
5. **形成正式报告。** 报告任务数、簇数、有效配对数、工具池重复数、运行重复数、点估计、置信区间和检验结果。

### 4.2 混合效应模型

混合效应模型直接读取未平均的原始运行行：

```text
原始运行结果
→ 保留pool_repeat
→ 保留model_run_repeat
→ 通过固定效应和随机效应处理重复结构
```

不得把A—E均值或运行重复均值作为混合效应模型输入，否则会丢失工具池和运行重复层面的变异。

主要Bootstrap簇固定为：

```text
minimal_pair_group
→ 不属于最小差异组时使用单任务稳定簇标识
```

工具路由结果另做`target_tool_family`簇级敏感性分析。主结果始终采用问题组簇级Bootstrap，不能根据显著性在两种簇定义中选择。若样本存在跨问题组共享工具家族，须在样本量附录中报告家族聚集带来的设计效应。

明确禁止：

- 将`任务 × 工具池 × 运行重复`全部平铺为独立样本；
- 先分别对条件取无法配对的总体平均，再计算差值；
- 用模型重复多数投票替代主要准确率；
- 在观察结果后更换H3工具规模或H4工具池类型；
- 从多个Bootstrap簇定义中事后选择最有利结果。

---

## 5. 缺失、失败与重复运行

- 已被供应商接受但执行失败的请求保持`request_status=accepted`，并在`execution_status`中区分模型失败、供应商失败、超时和无效响应；主要端到端分析按失败计；
- 因平台级故障而从未被供应商接受的请求标记为`request_status=not_accepted`且`execution_status=null`，不填造结果；
- 一个条件缺失时，对应配对不进入该项配对效应计算，并报告缺失数量、原因和受影响条件；
- 不得只对表现不佳的方法或条件选择性重跑；
- 若需恢复基础设施缺失，必须按预先记录的批次规则恢复该批次全部受影响条件，并保留原始失败记录。

正式分析需同时给出：

1. 端到端主要结果；
2. 排除纯基础设施缺失后的敏感性分析；
3. 各方法、条件的缺失和供应商失败率。

---

## 6. H3确认性模型

H3模型只读取：

```text
pool_design = controlled_dose
tool_pool_size = 120
```

确认性模型为：

```text
selection_correct
~ method
+ near_neighbor_type
+ near_neighbor_count
+ near_neighbor_type × near_neighbor_count
+ 其他预注册协变量
+ 随机截距(minimal_pair_group)
+ 随机截距(target_tool_family)
+ 随机截距(pool_family)
+ 随机截距(model_run_repeat)
```

主要计划对比固定为8近邻条件下的`functional_overlap − lexical`，按预注册方法集合计算边际对比。方法特异性对比作为次要结果。

---

## 7. H4确认性模型

H4模型只读取：

```text
pool_design = mixed_realistic
```

确认性模型为：

```text
selection_correct
~ method
+ log(tool_pool_size)
+ method × log(tool_pool_size)
+ 其他预注册协变量
+ 随机截距(minimal_pair_group)
+ 随机截距(target_tool_family)
+ 随机截距(pool_family)
+ 随机截距(model_run_repeat)
```

H4预注册三个单侧计划对比：

```text
D_H4_hierarchical − D_H4_full_schema > 0
D_H4_hierarchical − D_H4_lexical_top5 > 0
D_H4_hierarchical − D_H4_dense_top5 > 0
```

三项检验构成同一个确认性家族，统一使用Holm方法校正。只有三项点估计均大于0且Holm校正后的单侧`p < 0.05`，才支持“层次化路由相对于三类基线均具有更好的规模稳定性”。每项同时报告未校正和校正后的`p`值、直接差值与双侧95%问题组簇级Bootstrap置信区间。

如H3或H4模型不收敛，应报告原模型、预先规定的简化顺序和最终模型，不得根据显著性任意增删固定效应，也不得在两项假设之间混用工具池数据。

---

## 8. 脚本接口与验收

### 8.1 最小实现包

当前最小实现位于`Tools/core_freeze/`，包含输入Schema、状态校验、原始配对、描述性聚合、问题组簇级Bootstrap、H4三项Holm校正、合成测试和报告模板。

最小实现中的配对符号检验只用于验证方向、配对和多重校正代码，不能替代第6、7节规定的正式混合效应模型。正式模型未运行时，报告必须写入：

```text
formal_mixed_effect_model.status = not_run
cf11_status = in_progress
```

### 8.2 正式输出

正式统计实现至少输出：

- `h3_direct_contrast.csv`：功能重叠8与词法8的逐配对差值；
- `h3_baseline_contrasts.csv`：两类近邻相对`none, 0`的辅助效应；
- `h4_scale_stability_mixed.csv`：各方法17→120的逐配对差值；
- `run_repeat_summary.csv`：逐运行重复汇总；
- `cluster_bootstrap_summary.csv`：簇级Bootstrap结果；
- `missingness_audit.csv`：缺失、供应商失败和恢复记录；
- `confirmatory_report.json`：样本数、估计量、置信区间、检验方向和版本元数据。

统计脚本验收必须覆盖：

- 人工构造的正、负、零差值；
- A—E工具池重复不会被当成五个独立任务；
- 模型重复不会被多数投票替代；
- 打乱行顺序不改变结果；
- 缺少任一配对条件时能够识别并审计；
- H3只能读取120工具`controlled_dose`确认性条件；
- H4只能读取`mixed_realistic`的17与120工具条件。
