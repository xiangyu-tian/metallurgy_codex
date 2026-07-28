# CF-11最终化安全与治理加固证据

## 记录状态

- 日期：2026-07-28
- 对象：`Tools/core_freeze/finalize_cf11.py`
- 治理模式：`protected_repository_review`
- 结论：复审提出的四项正式使用前约束及角色独立性建议已实现；CF-11整体继续保持`in_progress`

---

## 1. Manifest路径边界

每个manifest文件名必须：

- 是非空相对路径；
- 不含Windows驱动器或绝对路径；
- 不含POSIX绝对路径；
- 不含`..`；
- 解析真实路径后仍位于`analysis_dir`内；
- 指向实际文件；
- 不得通过符号链接逃逸；
- 不得用多个名称解析到同一个文件。

程序拒绝：

```text
../outside.csv
C:\absolute\file.csv
/absolute/file.csv
```

---

## 2. 审批时间与时区

分析报告和四份审批记录的时间均必须是带时区的ISO-8601时间。

固定顺序：

```text
analysis.generated_at
≤ candidate_evidence.recorded_at
≤ statistics_review.recorded_at
≤ project_approval.recorded_at

analysis.generated_at
≤ candidate_evidence.recorded_at
≤ report_review.recorded_at
≤ project_approval.recorded_at
```

统计审查和报告审查可以并行，彼此不规定先后；项目审批必须晚于或等于两项审查。

---

## 3. 防覆盖与最终化标识

最终化输出使用文件独占创建模式：

```text
open(mode="x")
```

同一路径已存在时直接拒绝，不提供普通覆盖参数。正式`passed`记录因此不能被静默替换。

每个最终化记录包含：

```text
finalization_id = CF11-<20位确定性摘要>
```

该标识由以下内容共同导出：

- 分析报告哈希；
- manifest哈希；
- 四份审批记录的内容哈希。

相同分析和相同审批记录产生相同标识；任一证据变化都会产生不同标识。

---

## 4. 内部审批记录模式

证据字段统一使用：

```yaml
governance_mode: protected_repository_review
reviewer:
reviewer_role:
organization_or_team:
review_scope:
recorded_at:
```

固定角色：

| 证据 | `reviewer_role` |
| --- | --- |
| 真实候选干跑 | `experiment_executor` |
| 统计审查 | `statistics_reviewer` |
| 报告审查 | `report_reviewer` |
| 项目审批 | `project_approver` |

至少强制：

```text
statistics reviewer ≠ project approver
```

比较时忽略姓名大小写和首尾空白。

---

## 5. 非密码学声明

最终记录明确写入：

```text
evidence_assurance =
repository_governed_records_not_cryptographic_signatures
```

JSON内容哈希只验证内容一致性，不能证明人员身份。证据文件和最终化记录必须通过：

- 受保护Git分支；
- 仓库角色权限；
- Git签名提交；
- 项目审批流程；

进入正式仓库。当前脚本不声称验证Git托管平台权限或提交签名本身。

---

## 6. 针对性测试

```text
Ran 6 tests
OK
```

覆盖：

- 完整受治理审批记录可以生成最终化结果；
- 被篡改产物被拒绝；
- 已有最终化记录禁止覆盖；
- Windows、POSIX和父目录路径逃逸被拒绝；
- 无时区时间被拒绝；
- 审批时序错误被拒绝；
- 统计审查人与项目审批人为同一人时被拒绝；
- 最终记录包含确定性`finalization_id`和非密码学声明。

完整Core Freeze测试集：

```text
Ran 21 tests in 64.252s
OK
```

既有离线回归：

```text
Ran 44 tests
OK
Golden benchmark: 138 cases, 17 models, baseline 2.0.0
```

Python编译、R 4.6.1及13个锁定依赖、4个JSON文件和Markdown围栏检查均通过。

---

## 7. 当前状态

```yaml
design_specification: passed
estimand_definition: passed
sensitivity_specification: passed
engine_implementation: passed
synthetic_integration: passed
artifact_contract: passed
finalization_implementation: passed
real_candidate_dry_run: pending
statistical_review: pending
report_review: pending
approval: pending
overall: in_progress
```

本轮只加固审计与治理约束，不改变H3/H4统计设计。后续工作重心继续转向CF-01、CF-02。
