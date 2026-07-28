# CF-01 / CF-02 首轮试验包准备证据

## 1. 结论

本轮已把Core Frozen工作从CF-11统计实现切换到CF-01/CF-02候选数据准备：

```yaml
cf01:
  task_list: prepared
  dual_annotation: pending
  agreement_analysis: pending
  adjudication: pending
  overall: in_progress

cf02:
  task_list: prepared
  independent_routing_review: pending
  pool_construction: blocked
  overall: in_progress

core_frozen: false
```

准备态自动校验通过不等于双人标注、工具池构造或冻结验收通过。

## 2. 输入盘点

输入资产：

- 旧版工具调用数据：`Tools/benchmarks/tool_calling_cases.json`；
- 旧版样本数：120；
- 旧版主要字段：`should_call_tool`、`expected_models`和工程行为字段；
- 当前注册且可执行的工具数：17；
- 当前完成CF-05联合审核的工具数：0。

旧版标签只作为来源追溯和迁移提示，不直接升级为Dataset 2.0金标准。

## 3. CF-01准备结果

已冻结20例Track A候选任务，管理员覆盖计划包含：

- `none / optional / required`；
- `answerable / ambiguous_request / missing_task_information`；
- `sufficient / missing_execution_input / ambiguous_execution_input`；
- `available / unavailable / uncertain`；
- `normal / review_required`；
- 5组最小差异问题。

样本同时包含旧数据适配题和为2.0边界轴专门编写的新题。管理员覆盖计划仅用于检查样本设计，不是预先写定的金标准。

为避免标签泄漏，文件分为：

- 标注者可见任务；
- 管理员覆盖清单；
- 标注者A原始模板；
- 标注者B原始模板；
- 独立裁决模板。

两份标注模板均保持`not_started`和空标签，未伪造人工标注结果。

## 4. CF-02准备结果

已从旧版单工具任务中冻结20个目标任务，覆盖当前17个实现工具，并增加热容、反应热力学和平衡常数等相似家族的重复目标。

旧版`expected_models`被单独写入`track_b_legacy_review_hints.json`，字段名称明确标记为`unverified`。新的：

- `acceptable_tools`；
- `unacceptable_near_neighbors`；
- 六项相似度评分；
- 路由理由；

均保持空白，等待计算机方向与冶金方向成员独立审核。

构造契约已经固定：

- 17/50/100/120四个嵌套规模；
- A—E五个工具池重复；
- `none-0`；
- `lexical-4/8`；
- `functional_overlap-4/8`；
- `mixed_realistic`；
- 目标工具、近邻剂量、工具ID和严格嵌套校验。

## 5. 已确认阻塞

当前只有17个实现工具，且这些工具尚未完成CF-05联合审核。与120工具要求相比缺少103个工具。因此：

```text
17工具准备态：可执行
50/100/120工具池构造：阻塞
CF-02 passed：不允许
```

校验程序在当前快照上运行`--stage constructed`会主动拒绝，防止使用占位工具、重复入口或弱相关近邻凑数。

## 6. 自动校验

新增：

- `Tools/core_freeze/prepare_cf01_cf02_pilot.py`；
- `Tools/core_freeze/validate_cf01_cf02_pilot.py`；
- `Tools/core_freeze/tests/test_cf01_cf02_pilot.py`。

准备态校验检查：

- 两个Track均至少20个唯一任务；
- 标注者文件不含预期标签；
- A/B模板任务集合一致且未预填；
- Track A覆盖全部标签轴和最小差异组；
- 旧数据SHA-256未变化；
- Track B旧提示与金标准分离；
- 工具快照计数、CF-05状态和103工具缺口一致；
- 池规模、0/4/8条件和A—E重复契约未被修改。

标注态校验将计算裁决前：

- 五个核心单标签字段的Cohen's kappa；
- 五个字段的原始一致率；
- `allowed_actions`和`boundary_flags`的平均Jaccard；
- 逐任务分歧清单。

构造态校验还会验证全部必需工具池记录及严格嵌套关系。

验证结果：

```text
准备态校验：passed
本轮新增试验包测试：7项通过
完整Core Freeze回归：28项通过
既有正式离线回归：44项通过
Golden benchmark：138 cases，17 models，baseline 2.0.0
```

完整Core Freeze与既有离线回归均采用仓库正式入口串行执行。全目录
`unittest discover`不是既有离线回归入口；正式入口保持为
`Tools/run_baseline_tests.py`。

## 7. 下一步

1. 指定两名互相隔离的Track A标注者；
2. 完成20例原始标注并生成裁决前一致性报告；
3. 指定Track B计算机方向与冶金方向评审者；
4. 并行推进CF-05工具清单审核和真实工具扩充；
5. 达到120个审核通过工具后再构造0/4/8及现实混合池；
6. 全过程保持CF-01、CF-02为`in_progress`，不得提前升级Core Frozen。
