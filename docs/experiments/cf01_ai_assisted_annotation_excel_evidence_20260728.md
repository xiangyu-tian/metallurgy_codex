# CF-01 单专家＋双AI辅助标注Excel证据

## 1. 当前状态

已接收两份AI独立辅助标注：

- `Tools/core_freeze/pilot_v1/track_a_annotator_a_AI-A.json`
- `Tools/core_freeze/pilot_v1/track_a_annotator_b_AI-B.json`

两份文件均包含20个唯一任务，任务ID与冻结的Track A任务清单一致。它们是AI辅助原始记录，不是两名人类标注者的结果。

当前状态保持：

```yaml
cf01:
  ai_a_annotation: received
  ai_b_annotation: received_with_metadata_gap
  human_blind_annotation: pending
  human_adjudication: pending
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
| AI-A | 20 | 通过 | 完整 | `B2D0EFA04C2FBEF120B32D7512DC3E023F2910EFF3C2BC6064D466A6496917DC` |
| AI-B | 20 | 通过 | 缺少模型/角色/起止时间等顶层元数据 | `5839907305FA061E84BA1448F2878C5CAA2016F6234BF51508A7F9C118575416` |

AI-B的缺失元数据不得由实现者猜测填写，应由实际调用者根据运行记录补录。

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

共有13个任务在核心单标签、动作集合或边界标志中至少存在一项分歧。

结果表明：

- 两个AI对证据需求和风险判断高度稳定；
- 能力状态一致性不足，不能直接合并；
- 边界标志分歧较多；
- AI-A把20题全部标为`high`置信度，需要人类检查其置信度校准；
- 人类首轮盲标和最终裁决不可省略。

这些数值不能表述为双人类标注一致性，也不能直接用于通过CF-03。

## 4. Excel产物

### 人类盲标工作簿

路径：

```text
outputs/cf01_annotation_20260728/track_a_human_blind_annotation.xlsx
```

SHA-256：

```text
CB9FF1CEB04BB167E56780AE058C1E949DCB4F5FB85EE683D82CE645CEACCAA5
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
D7FC1BEF44B14E4B658374777D8D99E194D650BA93FC0C725E621AFE60CD6E7D
```

包含：

- AI—AI一致性摘要；
- 13题核心分歧审查表；
- 20题逐字段并排比较；
- AI-A完整原始表；
- AI-B完整原始表；
- 供人类填写的最终决定和裁决理由列。

## 5. 验证

两个工作簿均使用固定源JSON生成，并完成：

- 输入任务数、唯一ID和核心枚举校验；
- 关键区域值与公式检查；
- 公式错误扫描；
- 所有8个工作表的视觉渲染检查；
- 导出后文件哈希记录。

## 6. 下一步

1. 唯一人类标注者只打开`track_a_human_blind_annotation.xlsx`；
2. 完成20题并保存不可变原始版本；
3. 人类首轮完成前不得打开AI复核工作簿；
4. 首轮保存后打开`track_a_ai_comparison_review.xlsx`；
5. 优先审查能力状态、边界标志及13个分歧任务；
6. 人类确认最终标签和裁决理由；
7. 将Excel转换为正式JSON，再执行`--stage annotated`校验；
8. 以协议偏离形式说明采用单专家＋双AI辅助，而非双人类标注。
