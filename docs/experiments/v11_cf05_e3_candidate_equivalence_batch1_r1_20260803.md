# v1.1 CF-05 E3 第一批候选等价性本地验证

## 结论

第一批 5 个候选已在隔离、完整锁定的 Python 环境中完成离线验证：

```yaml
run_id: V11-CF05-E3-EQUIVALENCE-BATCH1-R1-20260803
status: completed_nonconfirmatory_equivalence_evidence
candidate_count: 5
unique_reference_case_count: 21
candidate_case_comparison_count: 25
comparison_pass_count: 18
comparison_fail_count: 7
exact_equivalent_over_frozen_scope: 1
partial_equivalent_overlap_only: 1
not_equivalent_over_frozen_scope: 3
external_api_calls: 0
formal_pool_generation_allowed: false
core_frozen: false
```

25 次比较不是 25 条新案例。冻结参考集共有 21 条唯一案例；两个 A003 候选分别复用了同一组 4 条案例，因此候选—案例比较总数为 25。

## 候选判定

| 候选 | 目标 | 通过/总数 | 判定 | 后续含义 |
|---|---|---:|---|---|
| `SRC-PINT-001` | A001 | 6/6 | `exact_equivalent_over_frozen_scope` | 可进入“可接受工具候选”审查，不自动成为正式工具 |
| `SRC-PMG-001` | A002 | 4/5 | `not_equivalent_over_frozen_scope` | `Fe0`边界行为不同，不能作为A002等价工具 |
| `SRC-RDKIT-004` | A003 | 2/4 | `not_equivalent_over_frozen_scope` | 原子量结果存在差异，且化学式到SMILES适配器不具一般性 |
| `SRC-PMG-002` | A003 | 1/4 | `not_equivalent_over_frozen_scope` | 三条正常案例均超出冻结数值容差，原子量口径不同 |
| `SRC-PMG-003` | A004 | 5/6 | `partial_equivalent_overlap_only` | 正常重叠域可用，但空组成边界不同，只能作为条件性子域候选 |

## 环境与可复现性

验证环境位于项目内的忽略目录`.venv-e3-candidates`，没有修改平台主`.venv`。环境固定为Python 3.11.15和59个精确版本发行包；完整锁文件为：

```text
Tools/core_freeze/e3_routing/candidate_validation_requirements_lock.txt
```

锁文件SHA-256：

```text
cf7e10e2217306bb3516875eca513ee085be7ca57b5225777fd16cfa1331c0b3
```

本地重跑命令：

```powershell
& '.\.venv-e3-candidates\Scripts\python.exe' -m Tools.core_freeze.e3_routing.run_e3_candidate_equivalence --output-dir '<new-output-dir>'
```

执行器在运行前会验证测试计划、参考案例和完整依赖锁的SHA-256，并拒绝缺包、多包、版本不符或Python版本不符的环境。

## 治理边界

本轮只形成开发阶段、非确认性的等价性证据：

- 1个精确等价候选仍需独立性审查、正式ID和契约注册后才能计入可接受工具集合；
- 1个部分等价候选只能限定到明确子域，不能扩展为完整目标工具；
- 3个不等价候选不会自动成为不可接受近邻，仍需“目标有效、候选无效”的任务夹具；
- 正式目录新增数、近邻槽位回填数均为0；
- CF-05仍为`in_progress`，词法缺口和契约错配缺口仍为30/40。

## 下一步

1. 为`SRC-PINT-001`完成独立性与正式契约准入审查；
2. 为`SRC-PMG-003`冻结允许子域，防止把部分等价误报为完整等价；
3. 对3个不等价候选构造目标有效、候选无效的确定性夹具；
4. 实现其余12项候选契约的最小包装器并执行正常、边界和失败案例；
5. 只有关系夹具和独立性审查通过后，才允许回填0/4/8近邻池。

## 产物

```text
outputs/v11_cf05_e3_equivalence_batch1_r1_20260803/
```

产物manifest：

```text
outputs/v11_cf05_e3_equivalence_batch1_r1_20260803/artifact_manifest.json
```

Manifest SHA-256：

```text
ec31a6ab043a322be256569f3e7cdbc04a0f1b3749461d5a208ac6810c19e743
```
