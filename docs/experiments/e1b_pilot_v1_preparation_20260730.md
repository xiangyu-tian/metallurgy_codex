# E1b pilot v1 任务准备记录

## 状态

```yaml
dataset_id: E1B-PILOT-V1-20260730
protocol_version: research_protocol_v1.1-rc1
dataset_status: prepared
task_count: 14
condition_run_cells_before_repeats: 28
model_runs_completed: 0
core_frozen: false
```

## 目的

该数据包用于首轮验证：

> 在相同机器可评分任务上，`Forced Verified Tool + Oracle Parameters`
> 相对于`No Tool`是否提高最终答案正确率、稳定性或可追溯性。

这一比较隔离“验证工具结果可用”的收益，不把工具选择错误和参数生成错误混入主要效应。

## 真值来源

所有任务均来自`VERIFIED-CORE-V1-20260730`通过的成功参考案例。任务不使用：

- AI-A或AI-B的主观调用标签；
- 非专业人员逐题判断；
- 生产工具自生成的参考输出；
- 开放式冶金建议。

每条任务保存参考案例ID、合同哈希、Oracle参数、结构化答案Schema和评分容差。

## 当前任务分布

| 工具 | 任务数 | 核心输出 |
| --- | ---: | --- |
| A001 | 4 | 换算数值 |
| A002 | 2 | 元素计量映射 |
| A003 | 3 | 摩尔质量 |
| A004 | 2 | 归一化组成 |
| B019 | 3 | 两相分数 |

其中A004和B019包含共同标度变换案例，可检查比例不变性；A001包含仿射温标案例。

## 尚未完成

1. 固定首轮模型、temperature、seed支持策略和超时；
2. 实现统一JSON回答提取与自动评分；
3. 设定开发性重复次数并运行API；
4. 按任务和工具家族报告成对差异；
5. 根据波动决定正式重复次数与扩展任务量；
6. 将收益估计数据与后续门控评价数据隔离。

因此当前不能报告`Accuracy Gain`，只能报告“任务接口已准备完成”。

## 后续执行记录

本准备记录形成后，项目已经实现JSON提取、自动评分、成对运行、失败审计和源码快照，
并完成`e1b-pilot-generator-v1.0.2`的三次开发重复。结果与任务修订审计见：

```text
docs/experiments/e1b_development_results_v102_20260730.md
```

本节不改变上方准备时点的状态；正式重复次数和确认性样本量仍未冻结。
