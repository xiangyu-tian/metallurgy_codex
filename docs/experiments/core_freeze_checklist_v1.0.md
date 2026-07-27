# Core Frozen 证据检查清单 v1.0

## 文档状态

- 版本：`1.0-rc1.1`
- 日期：2026-07-27
- 当前阶段：研究方案原则冻结，经验验证尚未冻结
- 目标状态：`1.0-core-frozen`
- 暂停事项：在本清单通过前，不继续M4.6C，不增加新的主线功能

本清单把冻结条件转化为可核验的证据门槛。勾选项目必须同时给出证据文件、Git提交、执行人或审批人和日期；仅有口头结论不能视为完成。

---

## 1. 版本兼容与来源清单

### 1.1 候选冻结文件

| 文档 | 版本 | 源Git提交 | SHA-256 |
| --- | --- | --- | --- |
| `docs/experiments/research_protocol_v1.0.md` | `1.0-rc3.1` | `2456f4c2e474c3f03f6b267240c965da69cc2b40` | `1B4D83FD39C9FA32A4587791AA719A88557CB61849D31C24F3D305CB9A48CEAF` |
| `docs/experiments/dataset_v2_annotation_policy_v1.0.md` | `1.0-rc3` | `2456f4c2e474c3f03f6b267240c965da69cc2b40` | `29ECF7BC24D83B902B6C3F1BE26A0023570A0D5E669A9B21FC666A4193265CE8` |

兼容性判断：

```text
research_protocol: 1.0-rc3.1
dataset_policy: 1.0-rc3
compatibility_status: approved_for_freeze_validation
```

H3、H4在`rc3.1`中的修订只固定统计比较，不改变数据表结构和标签语义，因此数据规范继续保留`rc3`。若上述任一文件内容发生变化，必须重新计算哈希并判断是否需要新版本。

### 1.2 正式审批记录

| 角色 | 姓名 | 结论 | 日期 | 签署证据 |
| --- | --- | --- | --- | --- |
| 冶金专业审查人 | 待填写 | 待审批 | 待填写 | 待填写 |
| 计算机/人工智能审查人 | 待填写 | 待审批 | 待填写 | 待填写 |
| 项目负责人 | 待填写 | 待审批 | 待填写 | 待填写 |

当前的结构性评审结论可以支持进入冻结验证，但不能代替以上正式签署。

---

## 2. Core Frozen总门槛

状态值统一使用：

- `pending`：尚未开始；
- `in_progress`：已有执行记录但未达到验收标准；
- `passed`：证据完整且达到验收标准；
- `failed`：已执行但未达到验收标准；
- `waived`：经联合书面审批后豁免，并记录原因和影响。

| ID | 冻结证据 | 最低验收标准 | 当前状态 | 证据路径/提交 |
| --- | --- | --- | --- | --- |
| CF-01 | Track A双人试标 | 至少20个样本；覆盖主要标签组合和最小差异组；保留两名标注者原始结果 | `pending` | 待生成 |
| CF-02 | Track B任务与工具池试构造 | 至少20个目标任务；含可接受工具、不可接受近邻、相似度评分、0/4/8近邻和现实混合池 | `pending` | 待生成 |
| CF-03 | 标注一致性检验 | 裁决前统计：核心单标签`κ ≥ 0.75`、集合字段平均Jaccard`≥ 0.80`、关键类别原始一致率`≥ 0.70`；保留分歧与裁决记录 | `pending` | 待生成 |
| CF-04 | 现有120例迁移审计 | 保留旧数据；完成2.0字段首轮映射、来源记录和逐例审计；不得直接视为正式金标准 | `pending` | 待生成 |
| CF-05 | 120工具联合审核通过 | 完成计算机与冶金方向双人独立审核、冲突裁决和最终清单确认；至少120个工具的`count_status=accepted`，且均具备独立入口、科学能力、输入输出契约、适用域、正常测试和边界测试 | `pending` | 待生成 |
| CF-06 | Full Schema API可行性 | 实测17/50/100/120；记录函数数量限制、上下文、Schema Token、延迟、错误和`tool_choice=none`行为 | `pending` | 待生成 |
| CF-07 | Taxonomy泄漏审计 | 检查类别名称、描述和示例是否泄漏目标工具；记录发现、修订和复审结果 | `pending` | 待生成 |
| CF-08 | 政策动作生成器测试 | 能力模式`allowed_actions`基准矩阵的所有规则均有自动测试；冲突优先级与多标签组合可复现 | `pending` | 待生成 |
| CF-09 | 先导实验与功效分析 | 估计类别分布、标注难度、Schema初步效应、重复波动、规模效应和设计效应 | `pending` | 待生成 |
| CF-10 | 样本量附录 | 生成并审批`sample_size_addendum_v1.0.md`，固定正式样本数及依据 | `pending` | 待生成 |
| CF-11 | 统计接口与报告模板 | H3/H4统计接口、输入校验、聚合测试和报告模板通过审查 | `in_progress` | `docs/experiments/statistical_analysis_interface_v1.0-rc1.1.md`；`docs/experiments/glmm_engine_spec_v1.0-rc1.md`；`Tools/core_freeze/`；`docs/experiments/cf11_minimum_test_evidence_20260727.md`；`docs/experiments/cf11_glmm_test_evidence_20260727.md` |

只有CF-01至CF-11全部为`passed`或具有正式联合审批的`waived`时，才能申请`1.0-core-frozen`。

---

## 3. 分项执行记录

每项冻结证据均使用以下记录结构，不能只修改总表状态：

```yaml
check_id:
status:
owner:
reviewer:
started_at:
completed_at:
input_version:
evidence_files:
git_commit:
acceptance_result:
deviations:
follow_up:
```

### 3.1 Track A试标包

样本选择至少覆盖：

- `none / optional / required`；
- `answerable / ambiguous / missing`；
- 执行信息充分与不足；
- 能力可用、不可用和不确定；
- 普通与高风险；
- 最小差异问题组。

必须输出：

- 冻结的试标样本清单；
- 两名标注者互相隔离的原始标注；
- 一致性统计；
- 分歧清单和裁决；
- 指南修改建议及是否影响标签语义的判断。

### 3.2 Track B试构造包

每个目标任务必须能够追溯：

- 可接受工具集合；
- 不可接受近邻；
- 相似度评分依据；
- 0/4/8词法近邻池；
- 0/4/8功能重叠近邻池；
- `mixed_realistic`工具池；
- 17/50/100/120嵌套关系；
- A—E工具池随机重复。

若不足以为确认性任务构造8个词法近邻和8个功能重叠近邻，应记录目标工具、缺口数量和原因，不得用弱相关工具凑数。

### 3.3 工程可行性记录

Full Schema检查使用同一模型、同一工具描述版本和可比较的请求配置。至少记录：

- 供应商、模型、接口和请求时间；
- Schema数量、序列化字节数和Token数；
- 总上下文Token及供应商限制；
- 请求是否被接受；
- 首Token和总延迟；
- `tool_choice=none`时模型是否仍能读取Schema；
- Full Schema与Top-5是否使用相同工具描述；
- 错误类型和完整日志位置。

API密钥及其他凭据不得写入证据文件、日志、Git提交或报告。

### 3.4 先导实验记录

先导数据不能用于事后选择更有利的主要假设或工具池。若先导结果触发设计变更，必须：

1. 登记协议偏离；
2. 判断是否需要新协议版本；
3. 重新生成文件哈希；
4. 将受影响的先导样本排除出正式确认性测试集。

---

## 4. 推荐执行顺序

```text
联合书面审查与签署
→ 冻结Track A/B试验样本
→ Track A双人试标 + Track B工具池试构造
→ 120工具独立性审核 + API可行性 + 泄漏审计 + 政策测试
→ 现有120例迁移审计
→ 先导实验
→ 功效分析与样本量附录
→ 统计脚本和报告模板验收
→ Core Frozen联合审批
```

相互不依赖的审核可以同期进行，但每项必须独立保留证据。先导实验不得早于关键标签、工具池和API可行性问题完成。

---

## 5. 冻结决策记录

申请Core Frozen时填写：

```yaml
target_status: 1.0-core-frozen
research_protocol_version: 1.0-rc3.1
dataset_policy_version: 1.0-rc3
statistical_interface_version:
sample_size_addendum_version:
all_checks_resolved: false
open_deviations: []
freeze_commit:
freeze_date:
metallurgy_approver:
ai_approver:
project_owner:
```

在`all_checks_resolved`变为`true`且三方审批完成前，项目状态始终保持：

> 研究方案原则冻结，经验验证尚未冻结。
