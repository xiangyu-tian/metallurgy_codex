# CF-04 E2双层门控语义开发复核v1.4结果

## 1. 结论

v1.4完成55条单次开发复核，11项预注册晋级检查全部通过：

```yaml
run_id: E2-HYBRID-SEMANTIC-DEV-76C34AE0E04A47FE
completed_count: 55
provider_failure_count: 0
semantic_supported_flag_macro_f1: 0.96875
merged_flags_exact_count: 53
action_correct_count: 55
out_of_domain_recall: 1.0
unsupported_system_recall: 1.0
premature_call_count: 0
validation_dataset_access_count: 0
gate_checks_passed: 11
gate_checks_required: 11
decision: advance_to_validation_preparation
```

该结果只允许准备一份需要另行授权的独立验证开启包，不构成确认性性能结论，也不授权读取或运行40条独立验证候选。

## 2. v1.1至v1.4趋势

| 指标 | v1.1 | v1.2 | v1.3 | v1.4 |
|---|---:|---:|---:|---:|
| 语义宏F1 | 0.8295 | 0.7750 | 0.9167 | 0.9688 |
| 合并标志精确数 | 45 | 48 | 49 | 53 |
| 动作正确数 | 54 | 55 | 54 | 55 |
| OOD召回率 | 1.0000 | 0.6000 | 1.0000 | 1.0000 |
| unsupported召回率 | 0.8333 | 1.0000 | 1.0000 | 1.0000 |
| 通过晋级检查 | 8/11 | 8/11 | 10/11 | 11/11 |

v1.4的确定性上下文将v1.3的6条B019 OOD误报降为2条，同时恢复55/55动作正确。

## 3. 剩余两条误差

`E2V2-B019-03`和`E2V2-B019-09`均应只有`ambiguous_parameter`，模型额外给出`contract_defined_out_of_domain`。确定性策略仍派生为`clarify`，所以没有形成动作错误。

开发门已经通过，不能再根据这两条开发误差修订提示词、上下文或政策。后续独立验证必须使用当前冻结的v1.4实现，并完整报告成功和失败。

## 4. 防泄漏与执行审计

| 检查 | 结果 |
|---|---:|
| 实际运行任务 | 55/55 |
| 唯一任务ID | 55 |
| 契约视图 | 5 |
| `deterministic_context`视图 | 55 |
| 发送视图中的金标字段 | 0 |
| 验证任务ID | 0 |
| API凭据模式命中 | 0 |
| 运行及分析manifest哈希失败 | 0 |

运行未调用任何冶金工具，40条独立验证候选未交给模型。

## 5. 证据位置

- 运行产物：`outputs/v11_cf04_e2_hybrid_semantic_development_v1_4_20260803`
- 门控分析：`outputs/v11_cf04_e2_hybrid_semantic_development_analysis_v1_4_20260803`
- 运行manifest SHA-256：`02b637be9619aa11d6f714c328427978a2417eea0541455b6bb7635c291a75b3`
- 分析manifest SHA-256：`503a8fb333014dd29bebc431894f3434e0ce421d6487334a099ee6d19c9b4495`

## 6. 回归测试

| 范围 | 结果 |
|---|---:|
| Core Freeze回归 | 172 passed |
| 既有工具回归 | 99 passed，1 skipped |

旧工具测试此前依赖但未声明`pytest`，本轮已将`pytest>=8,<9`加入`Tools/requirements.txt`并在项目venv中安装，随后完整回归通过。

## 7. 状态

```yaml
CF-04: in_progress
development_advancement_gate: passed
independent_validation: pending_separate_authorization
confirmatory_inference_allowed: false
core_frozen: false
```
