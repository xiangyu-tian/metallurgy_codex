# CF-05 E3 多目标现实混合池开发开启包 v1

开启编号：`V11-CF05-E3-MULTITARGET-MIXED-OPENING-V1-20260810`

状态：`prepared_local_gate_passed_pending_external_authorization`

## 目的

A003单目标开发实验的96个单元全部正确，无法区分路由方法。该开启包将目标扩展到四个不同工具家族，用于检查路由方法能否从单一摩尔质量任务迁移到单位换算、化学式解析、成分归一化和杠杆规则计算。

本包只解决多目标开发验证，不替代H3的0/4/8近邻机制实验，也不执行H4确认性分析。

## 冻结设计

| 维度 | 内容 |
| --- | --- |
| 目标工具 | A001、A002、A004、B019 |
| 任务 | 每个目标2条，共8条 |
| 工具池 | `mixed_realistic` 17工具与120工具 |
| 方法 | Full Schema、Lexical Top-5、Dense Top-5、Hierarchical Top-5 |
| 模型重复 | 1次 |
| 运行单元 | 8 × 2 × 4 = 64 |
| 工具执行 | 禁止 |
| 外部API | 本轮未调用 |

### 代表任务

- A001：`kg→g`和`atm→Pa`，覆盖普通倍率与工程压力单位；
- A002：`Fe2O3`和`K4[Fe(CN)6]`，覆盖简单与嵌套化学式；
- A004：真实元素组成与抽象`matrix/trace`组成，覆盖pymatgen替代工具的适用域边界；
- B019：同一杠杆规则问题的fraction和percent两种输入标度。

## 候选视图

共生成50个路由可见候选视图：

- Full Schema：每个规模1个，共2个；
- Lexical Top-5：8任务 × 2规模，共16个；
- Dense Top-5：16个；
- Hierarchical Top-5：16个。

路由输入、候选视图和运行单元中不包含：

- 可接受工具集合；
- 目标工具字段；
- 评分规则；
- 期望参数；
- 参考答案。

## 本地召回门

| 方法 | 检查单元 | Target Recall@5 | Acceptable Recall@5 | 状态 |
| --- | ---: | ---: | ---: | --- |
| Lexical Top-5 | 16 | 1.000 | 1.000 | 通过 |
| Dense Top-5 | 16 | 1.000 | 1.000 | 通过 |
| Hierarchical Top-5 | 16 | 1.000 | 1.000 | 通过 |

该结果只证明正确工具进入模型可见的Top-5，不代表大模型最终一定会选对，也不是方法效果比较结果。

## API与统计边界

- CF-06已证明17/120原生函数Schema可以提交；
- 本轮外部API调用为0；
- 64个运行单元均为`not_executed`；
- 尚未生成正式外部运行结果；
- 尚未授权向DeepSeek发送任务或Schema；
- 只有一个现实混合池实例，没有A—E工具池重复；
- 不允许H3/H4确认性推断；
- `CF-05 = in_progress`；
- `Core Frozen = false`。

## 产物

目录：`outputs/v11_cf05_e3_multitarget_mixed_opening_v1_20260810/`

主要文件：

- `multitarget_routing_input_tasks.json`；
- `multitarget_mixed_selected_pools.json`；
- `multitarget_candidate_views.json`；
- `multitarget_routing_scoring_registry.json`；
- `multitarget_routing_run_cells.json`；
- `multitarget_local_retrieval_gate.json`；
- `execution_authorization_request.json`；
- `artifact_manifest.json`。

## 下一步

先提交并推送该离线开启包。若执行外部开发实验，需要另行明确授权以下固定范围：

> 将8条冻结开发任务、17/120现实混合工具Schema及三种Top-5候选视图，以64个一次性请求发送至DeepSeek `deepseek-v4-flash`；每个单元只尝试一次，不执行任何冶金工具，不访问独立验证集，并保存逐条响应用于离线评分。
