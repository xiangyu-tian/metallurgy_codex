# CF-01 双AI共识预标＋人工精简裁决Excel证据

最后更新：2026-07-30

## 1. 当前状态

已接收两份AI独立辅助标注：

- `Tools/core_freeze/pilot_v1/track_a_annotator_a_AI-A.json`
- `Tools/core_freeze/pilot_v1/track_a_annotator_b_AI-B.json`

两份文件均包含20个唯一任务，任务ID与冻结的Track A任务清单一致。它们是AI辅助原始记录，不是两名人类标注者的结果。

当前状态保持：

```yaml
cf01:
  ai_a_annotation: received
  ai_b_annotation: received_metadata_supplemented
  human_blind_annotation: skipped_by_pilot_deviation
  human_adjudication: completed_9_disagreements_plus_3_audits
  silver_conversion: passed
  label_tier: provisional_silver
  overall: in_progress

cf03:
  inter_human_agreement: not_available
  ai_ai_agreement: exploratory
  overall: pending

core_frozen: false
```

## 2. 原始文件审计

| 文件 | 任务数 | 结构 | 元数据 | SHA-256 |
| --- | ---: | --- | --- | --- |
| AI-A | 20 | 通过 | 模型确认为`deepseek-v4-pro` | `DD2567C1CBE7ECEBF54E2DF23B889845E5333AD2BC90C9A5B1175EB3FAB44EEB` |
| AI-B | 20 | 通过 | 模型身份和角色已补录；标注内容未改变 | `62CB40AB3ACBE0630876ACB277062CB204692D28F35B0E06E8559526ABDC3310` |

AI辅助试标不以时间字段作为准入门槛。两份记录中的时间值仅保留为来源记录，
不用于证明标签正确性，也不强制补造无法确认的时间。

## 3. AI—AI诊断性一致性

| 字段 | 一致数 | 原始一致率 | Cohen's kappa/平均Jaccard |
| --- | ---: | ---: | ---: |
| `evidence_requirement` | 20/20 | 1.000 | κ=1.000 |
| `answerability` | 19/20 | 0.950 | κ=0.864 |
| `information_status` | 19/20 | 0.950 | κ=0.912 |
| `capability_status` | 15/20 | 0.750 | κ=0.497 |
| `risk_status` | 20/20 | 1.000 | κ=1.000 |
| `allowed_actions` | 16/20完全一致 | 0.800 | 平均Jaccard=0.825 |
| `boundary_flags` | 8/20完全一致 | 0.400 | 平均Jaccard=0.718 |

共有13个任务至少存在一项差异，其中：

- 9题在核心单标签或`allowed_actions`中存在实质性分歧；
- 4题仅`boundary_flags`不同；
- `boundary_flags`是解释性多标签，不要求完全一致。

结果表明：

- 两个AI对证据需求和风险判断高度稳定；
- 能力状态一致性不足，不能直接合并；
- 边界标志存在多角度解释，应报告Jaccard而非把完全一致率作为门槛；
- AI-A把20题全部标为`high`置信度，需要人类检查其置信度校准；
- 当前首轮试验经流程偏离记录，跳过人工盲标，只保留实质性分歧裁决和分层抽查。

这些数值不能表述为双人类标注一致性，也不能直接用于通过CF-03。

## 4. Excel产物

### 人类盲标工作簿

路径：

```text
outputs/cf01_annotation_20260728/track_a_human_blind_annotation.xlsx
```

SHA-256：

```text
11A0EFB397204617F8F7D221E29D78D2A8937708FE6F5DD0EAEB8537A12FBA9C
```

包含：

- 填写说明和进度公式；
- 20题人工盲标表；
- 单标签下拉框；
- 多值字段填写约定；
- 完整标签字典；
- 不包含任何AI答案。

### AI复核工作簿

路径：

```text
outputs/cf01_annotation_20260728/track_a_ai_comparison_review.xlsx
```

SHA-256：

```text
7E3EF9A26A8A07ED2D211BE731AEC35512A938F88A7550A3CEE1BC04F51E92FB
```

包含：

- AI—AI一致性摘要；
- 13题核心分歧审查表；
- 20题逐字段并排比较；
- AI-A完整原始表；
- AI-B完整原始表；
- 供人类填写的最终决定和裁决理由列。

### AI共识＋人工精简裁决工作簿

路径：

```text
outputs/cf01_annotation_20260728/track_a_ai_consensus_human_adjudication.xlsx
```

SHA-256：

```text
0727B9E2074312C02B6FD46699539CEAF959752D83D2635DA432CBCE9EBFFCC7
```

包含：

- 9道核心标签或动作标签实质性分歧；
- 3道按证据需求分层、固定种子选取的AI全字段一致抽查；
- AI-A、AI-B逐题核心结论和理由；
- 共识标签预填、分歧单元格留空；
- 最终裁决理由、置信度和专业复核标记；
- 字段级差异和两份AI来源明细。

### 银标准JSON与验证报告

银标准候选集：

```text
Tools/core_freeze/pilot_v1/track_a_provisional_silver.json
SHA-256: B1EFF8D46B1BB34AC7C52D34C051AD641102237AD94154927B1935A08F6C9F24
```

验证报告：

```text
outputs/cf01_annotation_20260728/track_a_provisional_silver_validation.json
SHA-256: 21D03BDCC2BFF8D4E4FCE32949A6204C1E0D2BEF00FEA3854FDEC89650B8FB88
```

转换结果：

```yaml
status: passed
task_count: 20
human_adjudicated: 9
human_audit_confirmed: 3
ai_consensus_unreviewed: 8
adjudicator: 张三
policy_action_validation: passed
formal_cf01_eligible: false
formal_cf03_eligible: false
```

TA-PILOT-020因`0 K`明确超出Arrhenius适用域，记录了一项从默认
`clarify`到`refuse`的显式政策覆盖。覆盖理由随JSON保存，未静默修改。

## 5. 验证

三个工作簿均使用固定源JSON生成，并完成：

- 输入任务数、唯一ID和核心枚举校验；
- 9题实质性分歧和3题固定抽查契约校验；
- 20题银标准来源覆盖和唯一ID校验；
- 核心枚举、动作枚举和政策矩阵校验；
- 单一裁决者与来源文件SHA-256校验；
- 关键区域值与公式检查；
- 公式错误扫描；
- 所有14个工作表的视觉渲染检查；
- 导出后文件哈希记录。

银标准验证报告有0个错误和4项预注册限制说明：

- 空白`boundary_flags`保持`not_adjudicated`；
- `required_inputs`、`missing_inputs`和`coarse_capability`尚未裁决；
- 中文工作表`COUNTIF`在artifact-tool重新计算时显示`#NAME?`，转换不依赖这些摘要公式；
- 银标准不能替代正式双人类标注。

## 6. 下一步

1. 保留当前Excel、银标准JSON和验证报告的哈希绑定；
2. 使用银标准数据验证后续工程流程和先导实验；
3. 不使用本数据宣布CF-01、CF-03或Core Frozen通过；
4. 后续获得冶金专家资源时，优先复核9道分歧题和8道未人工审查的AI共识题；
5. 完成专业复核后另生成正式候选金标准，不覆盖当前银标准版本。
