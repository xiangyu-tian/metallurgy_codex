# v1.1 CF-01 / CF-02 自动审计证据

## 结论

v1.1 Core Freeze 的前两项门槛已经通过机器可复核审计：

```yaml
audit_id: V11-CF01-CF02-AUDIT-20260731
status: passed
cf01: passed
cf02: passed
core_frozen: false
```

本次通过不会把旧 Track A AI 共识银标升级为金标准，也不会把旧 Track B 人工模板当作确认性工具路由真值。

## CF-01：协议与数据规范兼容性

8/8项检查通过：

1. 研究协议版本为`1.1-rc1`；
2. 数据规范版本为`1.0-rc1`并明确配套v1.1协议；
3. 专家逐题标注已退出正式确认性关键路径；
4. G1、G2、C1和S1真值层级已定义；
5. 确认性结论只允许使用G1、G2和C1；
6. AI辅助标签保持`provisional_silver`；
7. 数据生产固定为契约优先、独立参考和AI只改写表达；
8. 协议与数据规范均保持`core_frozen=false`。

CF-01只证明治理口径一致，不证明具体实验已经完成。

## CF-02：verified_core与独立参考

11/11项检查通过：

- 工具数量：5，最低要求3；
- 工具：A001、A002、A003、A004、B019；
- 契约ID和工具ID唯一；
- 5个工具状态均为`verified_core`；
- 契约必需字段和契约哈希全部有效；
- 每个契约均有外部来源、验证范围和已知限制；
- 运行时重新验证通过；
- 正常与边界覆盖通过；
- 已发布验证报告通过；
- 已发布manifest哈希通过；
- 参考期望值独立冻结，不由生产工具生成。

验证结果：

```text
contracts = 5
reference_cases = 27
passed = 27
failed = 0
```

通过范围仅限五个工具各自`verification_scope`，不能扩大到其余12个已实现工具或103个规划工具。

## 治理迁移

旧`core_freeze_checklist_v1.0.md`已经包含版本升级通知，并继续作为历史清单保留。当前主线改由：

```text
core_freeze_checklist_v1.1-rc1.md
```

管理。新、旧CF编号语义不同，状态不能直接复制。

## 证据文件

```text
Tools/core_freeze/audit_v11_cf01_cf02.py
Tools/core_freeze/tests/test_v11_cf01_cf02_audit.py
outputs/v11_cf01_cf02_audit_20260731/audit_report.json
outputs/v11_cf01_cf02_audit_20260731/artifact_manifest.json
docs/experiments/core_freeze_checklist_v1.1-rc1.md
```

测试：

```text
v1.1 CF-01/02审计测试：4项通过
verified_core回归测试：15项通过
```

## 下一步

下一冻结项为CF-03：E1b基础任务与收益先导冻结。应复用已完成的E1b/E1c资产，完成：

- 任务家族清单；
- 收益估计与门控评价分区隔离；
- 重复波动汇总；
- 功效分析输入；
- 正式重复次数冻结。

不再继续旧的“双人专家逐题金标”路径。
