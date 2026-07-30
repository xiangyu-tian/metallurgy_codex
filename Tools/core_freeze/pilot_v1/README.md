# CF-01 / CF-02 首轮试验包

本目录是Core Frozen经验验证的首轮准备包，不是已经完成的金标准数据。

当前状态：

- CF-01：双AI共识＋人工精简裁决已形成20例`provisional_silver`候选集；由于没有双人类独立标注，CF-01仍为`in_progress`；
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

## 单专家＋双AI辅助的Excel流程

人手不足时，使用两个相互隔离的AI生成辅助标注，但AI不能冒充第二名人类标注者。当前原始记录为：

- `track_a_annotator_a_AI-A.json`
- `track_a_annotator_b_AI-B.json`

配套Excel文件位于`outputs/cf01_annotation_20260728/`：

- `track_a_human_blind_annotation.xlsx`：保留的完整人工盲标方案，不包含AI答案；
- `track_a_ai_comparison_review.xlsx`：20题AI-A/AI-B逐字段比较和诊断性一致性；
- `track_a_ai_consensus_human_adjudication.xlsx`：当前采用的精简裁决方案，包含9题实质性分歧和3题分层一致性抽查。

当前首轮试验采用：

```text
AI-A/AI-B核心标签一致
→ 暂定AI共识预标
→ 人工裁决9题实质性分歧
→ 人工抽查3题全字段一致样本
→ 标记需专业复核的任务
→ 生成provisional silver裁决结果
→ 转换为银标准JSON并运行专用完整性校验
```

三道抽查使用固定种子`CF01-AUDIT-V1`，在AI全字段一致样本中按
`none / optional / required`分层选择，固定为`TA-PILOT-001`、
`TA-PILOT-002`和`TA-PILOT-006`。

`boundary_flags`是解释性多标签，不使用完全一致率作为通过门槛。
AI—AI的Cohen's kappa和Jaccard只作为诊断值，不能写成双人类标注一致性。
该流程没有人工盲标，输出只能标记为`provisional_silver`，不能据此宣布
CF-01、CF-03或Core Frozen通过。

当前已生成：

- `track_a_provisional_silver.json`：20题银标准候选标签；
- `outputs/cf01_annotation_20260728/track_a_provisional_silver_validation.json`：转换与政策校验报告。
