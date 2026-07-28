# CF-01 / CF-02 首轮试验包

本目录是Core Frozen经验验证的首轮准备包，不是已经完成的金标准数据。

当前状态：

- CF-01：20例任务清单和两份隔离标注模板已准备，双人标注、一致性统计和裁决尚未执行；
- CF-02：20个目标任务和构造契约已准备；当前只有17个已实现工具，且尚无工具完成CF-05联合审核，因此50/100/120工具池不得构造；
- `core_frozen=false`。

## 文件隔离

标注者A和B只应收到：

- `track_a_tasks.json`
- 自己对应的`track_a_annotator_a.json`或`track_a_annotator_b.json`
- `docs/experiments/dataset_v2_annotation_policy_v1.0.md`

独立标注完成前，不应向标注者提供：

- `track_a_selection_manifest.json`：包含管理员预期覆盖目标，不是金标准；
- 另一名标注者的文件；
- `track_a_adjudication.json`；
- 旧版`should_call_tool`或模型实验结果。

Track B的`track_b_legacy_review_hints.json`只用于迁移审计。其中的
`legacy_expected_tools_unverified`不是Dataset 2.0的`acceptable_tools`，不得直接复制为金标准。

## CF-01执行顺序

1. 冻结本目录及输入文件哈希；
2. A、B两名标注者互相隔离填写各自文件；
3. 将`independence_status`改为`completed`，填写人员、角色和带时区的起止时间；
4. 运行准备态与标注态校验；
5. 保存裁决前一致性报告；
6. 形成分歧清单并由第三方裁决；
7. 填写指南修改建议，判断是否改变标签语义；
8. 经审核后才可申请把CF-01和CF-03的相应子项升级。

命令：

```powershell
& '.\.venv\Scripts\python.exe' `
  'Tools\core_freeze\validate_cf01_cf02_pilot.py' `
  'Tools\core_freeze\pilot_v1' `
  --stage annotated `
  --report 'output\core_freeze\cf01_agreement_pre_adjudication.json'
```

标注态校验会计算五个核心单标签字段的Cohen's kappa和原始一致率，以及
`allowed_actions`、`boundary_flags`的平均Jaccard。统计必须在裁决前保存。

## CF-02执行顺序

1. 先完成CF-05的120工具联合审核，不能把规划条目或重复入口当作独立工具；
2. 两名评审者独立确定`acceptable_tools`、不可接受近邻和六项相似度评分；
3. 裁决后构造0/4/8控制剂量池和`mixed_realistic`池；
4. 每个条件构造A—E五个重复，保证`17 ⊂ 50 ⊂ 100 ⊂ 120`；
5. 近邻不足时填写`missing_condition_log`，不得用弱相关工具凑数；
6. 完成后运行`--stage constructed`校验。

构造态校验要求每个任务包含：

- `none-0`、`lexical-4/8`、`functional_overlap-4/8`；
- 四个工具规模；
- A—E五套重复；
- `mixed_realistic`四个嵌套规模；
- 目标工具存在、近邻剂量准确、工具ID合法且工具池严格嵌套。

在当前17工具快照下，`--stage constructed`应当失败。这是设计要求，不是程序故障。
