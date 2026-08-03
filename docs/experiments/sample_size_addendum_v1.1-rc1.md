# v1.1样本量与重复次数附录

## 文档状态

- 版本：`1.1-rc1`
- 日期：2026-07-31
- 配套协议：`research_protocol_v1.1-rc1.md`
- 当前状态：E1b正式设计已批准，其余实验待补充
- CF-09：`in_progress`
- Core Frozen：`false`

本附录记录各实验正式样本量、模型重复次数和功效依据。不同实验必须分别完成审批；任何一个实验的批准不得自动外推到其他实验。

## 1. 当前覆盖矩阵

| 实验 | 样本量依据 | 正式重复次数 | 审批状态 |
|---|---|---:|---|
| E1a Schema暴露 | 尚无独立功效分析 | 待定 | `pending` |
| E1b工具收益 | 26个基础任务组先导及CF-08功效规划 | 3 | `approved` |
| E2执行准备度 | CF-04的40条独立任务R1已完成；R2/R3波动包待授权 | 待三次重复波动分析 | `pending` |
| E3大规模路由 | 待CF-05/CF-06工具池和API先导 | 待定 | `pending` |

因此，本附录已经冻结E1b，但尚未满足全项目CF-09通过条件。

## 2. E1b批准设计

### 2.1 主要对比

```text
Forced Verified Tool + Oracle Parameters
vs
No Tool
```

主要效应：

```text
Accuracy Gain
= Accuracy_ForcedVerifiedTool
− Accuracy_NoTool
```

### 2.2 已批准参数

```yaml
minimum_meaningful_accuracy_gain: 0.05
alpha: 0.05
test_direction: one_sided_positive_gain
target_power: 0.80
pilot_uncertainty_inflation: 0.15
independent_unit: base_task_group_id
base_task_groups: 120
verified_tool_families: 5
base_task_groups_per_verified_tool_family: 24
tasks_per_base_task_group: 2
task_count: 240
conditions: 2
model_run_repeats: 3
paired_repeat_count: 720
model_cell_count: 1440
approximate_planning_power: 0.8501
```

这里的120是基础任务组数，不是工具数。

### 2.3 选择依据

先导实验观察到：

- 26个基础任务组；
- 组等权平均收益11.54个百分点；
- 组间标准差20.42个百分点；
- 三次重复的任务加权收益均为13.33个百分点；
- 43/45个任务在三次运行中完全稳定；
- 任务内重复ICC为0.8744。

使用基础任务组作为独立单位，在5个百分点最小有意义效应、单侧`alpha=0.05`和80%目标功效下，正态规划近似需要104组。考虑先导样本较小，增加15%不确定性余量，并按五个工具家族平衡向上取整后，确定为120组。

三次模型重复用于记录随机波动；重复运行不能平铺为独立任务。高重复相关性说明新增预算应优先扩展任务组，而不是继续增加同一任务的重复次数。

## 3. E1b分配规则

每个`verified_core`工具家族分配24个基础任务组，每组构造2个预注册差异任务，共48个任务：

| 工具 | 基础任务组 | 任务数 | 三次重复下的成对重复 | 两条件模型单元 |
|---|---:|---:|---:|---:|
| A001 | 24 | 48 | 144 | 288 |
| A002 | 24 | 48 | 144 | 288 |
| A003 | 24 | 48 | 144 | 288 |
| A004 | 24 | 48 | 144 | 288 |
| B019 | 24 | 48 | 144 | 288 |
| 合计 | 120 | 240 | 720 | 1,440 |

任务生成器必须在API运行前固定：

- 工具和契约版本；
- 基础任务组ID和任务ID；
- 输入采样空间和随机种子；
- 精度政策；
- 参考公式、容差和评分规则；
- 数据切分；
- 运行配置和模型版本。

正式任务不得简单复制先导任务并将其声称为新的独立样本。

## 4. E1b统计规则

- 主要估计按基础任务组聚类；
- 三次模型重复先在任务内汇总；
- 工具家族必须分层报告；
- 同时报告任务加权与组等权结果；
- 报告效应量和95%置信区间；
- 负收益、零收益、失败和重试均保留；
- 单侧检验只用于预注册的“正收益”主要假设；
- 双侧95%置信区间仍必须报告；
- 不得因正式结果改变5个百分点阈值、任务组数量或重复次数。

## 5. 防循环要求

E1b正式收益任务不能同时承担门控规则的训练和独立性能证明：

```text
收益估计
≠
门控开发
≠
门控后置评测
```

如果未来使用正式E1b收益结果更新门控政策，必须另建未使用的评测集或采用预注册交叉拟合。

## 6. 计算预算

根据先导平均值，E1b正式设计预计：

- 约301,000 Token；
- 纯顺序API响应时间约20.8分钟；
- 实际运行时间另受限流、重试、并发和文件处理影响；
- API费用按执行时实际用量记录，不在本附录硬编码供应商价格。

## 7. 尚未冻结的实验

### E1a

需要先固定正式Schema条件、主要对比和有收益/无收益任务构成，再估计调用率与正确率差异所需样本量。

### E2

CF-04的缺参、歧义、超域、不支持和不可用任务链已经完成，40条独立任务R1结果为：LLM-only flags完全匹配37/40、动作39/40；双层门控flags完全匹配39/40、动作40/40。当前只完成一次模型运行，尚不能估计重复波动。

已准备R2/R3未授权开启包。若另行执行，将与R1合并为三次重复，估计任务内预测稳定性和各重复下的配对差。重复观测只能估计运行波动，不能当作新增独立任务；E2正式独立任务数仍须在三次重复分析后冻结。

### E3

需要完成CF-05工具近邻池和CF-06 API可行性先导，再按工具规模、近邻剂量、路由方法和目标工具家族确定样本量。

## 8. 审批绑定

E1b批准记录：

```text
Tools/core_freeze/approvals/v11_cf08_e1b_approval_20260731.json
```

批准记录绑定：

- CF-08分析Git提交；
- CF-08产物manifest哈希；
- CF-08功效报告哈希；
- 所有批准参数；
- 明确的批准范围和时间。

该记录是项目治理审批记录，不是密码学数字签名。

## 9. 状态结论

```yaml
CF-03:
  e1b_candidate_evidence: passed
  e1b_power_and_repeat_freeze: passed
  overall: passed

CF-08:
  e1b_component: passed
  e1a_component: pending
  e2_component: pending
  e3_component: pending
  overall: in_progress

CF-09:
  e1b_component: passed
  e1a_component: pending
  e2_component: pending
  e3_component: pending
  overall: in_progress

core_frozen: false
```
