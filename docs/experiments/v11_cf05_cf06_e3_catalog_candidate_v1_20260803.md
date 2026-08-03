# v1.1 CF-05/CF-06 E3契约目录候选v1

## 1. 结论

已从CF-05A锁定的120条预审清单生成E3路由目录候选和四个基础嵌套池：

```yaml
candidate_id: V11-CF05-CF06-E3-CATALOG-CANDIDATE-V1-20260803
status: candidate_generated_not_formally_eligible
catalog_entry_count: 120
pool_sizes: [17, 50, 100, 120]
external_api_calls: 0
```

该候选完成的是目录和API载荷的离线结构准备，不代表CF-05或CF-06已经通过。

## 2. 三类工具状态

| 状态 | 数量 | 可作为正式E3目标 | 可执行 |
|---|---:|---|---|
| `verified_executable_core` | 5 | 是 | 是，仅限冻结契约范围 |
| `implemented_tested_unreviewed` | 12 | 否 | 不允许进入正式执行评分 |
| `schema_only_planned` | 103 | 否 | 否 |

103条规划条目只使用`summary_stub_not_parameter_contract`，用于路由目录构造和Schema API容量先导。它们不能被称为已实现、已验证或可执行的专业计算工具。

生命周期标签保留在内部目录字段中，不写入模型可见的函数描述，避免模型仅凭“已验证”或“不可执行”等治理标签完成选择。

## 3. 嵌套池构造

基础池固定包含当前17个运行时注册工具。其余103条按以下预先规定且不读取模型结果的顺序加入：

```text
priority
→ scenario round-robin
→ source_row
```

生成关系为：

```text
Pool-17 ⊂ Pool-50 ⊂ Pool-100 ⊂ Pool-120
```

| 规模 | 已验证 | 已实现未验证 | Schema-only |
|---:|---:|---:|---:|
| 17 | 5 | 12 | 0 |
| 50 | 5 | 12 | 33 |
| 100 | 5 | 12 | 83 |
| 120 | 5 | 12 | 103 |

这些是`mixed_realistic`基础目录候选，不替代目标工具级的0/4/8契约近邻剂量池。

## 4. 自动检查

新增测试覆盖：

1. 120条目录的状态分层和计数；
2. 只有A001、A002、A003、A004、B019可作为正式目标和执行工具；
3. 17/50/100/120池的精确数量、唯一性和嵌套关系；
4. 120个OpenAI函数定义的结构合法性；
5. 产物manifest完整性及零API调用约束。

新测试结果：`5/5 passed`。

## 5. 当前阻塞项

正式使用前仍须完成：

- 25条`needs_family_review`条目的独立性复核；
- 针对每个已验证目标工具构造0/4/8契约近邻池；
- 为正式参数生成评分冻结可执行参数契约；
- 单独授权后执行CF-06的17/50/100/120 API可行性实测；
- 记录Schema Token、上下文、延迟、错误及`tool_choice=none`行为。

因此当前状态保持：

```yaml
CF-05: in_progress
CF-06: in_progress
E3_confirmatory_execution_allowed: false
core_frozen: false
```

## 6. 产物

目录：

```text
outputs/v11_cf05_cf06_e3_catalog_candidate_v1_20260803/
```

主要文件：

- `e3_schema_catalog_v1_candidate.json`；
- `e3_nested_pool_manifest_v1_candidate.json`；
- `openai_tools_pool_17.json`；
- `openai_tools_pool_50.json`；
- `openai_tools_pool_100.json`；
- `openai_tools_pool_120.json`；
- `build_report.json`；
- `artifact_manifest.json`。

`artifact_manifest.json`的SHA-256：

```text
cbebc748110bad4b853ab1f965119be02780af93a7492936f21bd7e73dd6fc15
```
