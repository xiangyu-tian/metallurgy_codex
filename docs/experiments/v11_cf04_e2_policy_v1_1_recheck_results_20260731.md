# v1.1 CF-04 E2 flags-only策略开发复核结果

## 结论

E2 flags-only策略v1.1的独立API开发复核已经完成：

```text
execution_status = completed
development_gate = passed_with_limitations
CF-04 = in_progress
Core Frozen = false
```

v1.1成功关闭了首轮最主要的输出协议问题，并显著改善了底层flags分类，尤其解决了`unsupported system`与一般契约超域的混淆。但动作层没有同步改善：`clarify`准确率下降，并出现一条缺参漏检导致的提前调用。因此，当前不能将CF-04标记为通过。

本次复核使用与v1相同的55条开发任务，只能用于策略开发与错误定位，不能作为无偏泛化或确认性效果证据。

## 1. 执行条件

| 项目 | 值 |
|---|---|
| Run ID | `E2-DEV-V11-RUN-876742250AA34387` |
| 数据集 | `E2-CONTRACT-BOUNDARY-PILOT-V1-20260731` |
| 模型 | `deepseek-v4-flash` |
| API | `https://api.deepseek.com` |
| Thinking | disabled |
| 任务数 | 55 |
| 重复数 | 1 |
| 模型输出字段 | `flags` |
| 状态和动作 | 从flags确定性派生 |
| 工具访问 | disabled |
| 确认性推断 | false |

执行前已经完成：

1. 候选提示词、Schema、配置和运行器哈希冻结；
2. 候选提交`a56442d`远程备份；
3. 用户明确授权外部发送范围；
4. 执行授权文件绑定精确哈希；
5. 无授权文件时拒绝运行的自动测试。

## 2. API完整性

| 指标 | 结果 |
|---|---:|
| 任务单元 | 55 |
| 完成 | 55 |
| 供应商失败 | 0 |
| 发生重试的任务 | 0 |
| API尝试总数 | 55 |
| Schema有效 | 55 |
| Schema有效率 | 100.00% |

所有模型响应均只包含：

```json
{
  "flags": []
}
```

或包含一个及以上合法flags的同结构对象。未再出现模型输出聚合型状态造成的Schema失败。

## 3. v1.1绝对结果

| 指标 | v1.1结果 |
|---|---:|
| Schema有效率 | 100.00% |
| flags完全匹配率 | 87.27%（48/55） |
| flags平均Jaccard | 92.73% |
| 支持类别Macro-F1 | 94.58% |
| 派生primary status准确率 | 87.27% |
| 派生action准确率 | 89.09% |
| Invalid Execution Rate | 2.00% |
| Premature Call Rate | 4.17% |
| OOD Call Rate | 0.00% |

按预期动作：

| 预期动作 | 正确/总数 | 准确率 |
|---|---:|---:|
| `call` | 5/5 | 100.00% |
| `clarify` | 18/24 | 75.00% |
| `refuse` | 26/26 | 100.00% |

## 4. 与v1语义回放基线的配对比较

比较基线不是v1的严格三字段得分，而是从v1响应中提取flags后得到的语义回放结果。这样比较的是事实分类变化，避免把已知的聚合状态格式错误混入方法差异。

| 指标 | v1语义回放 | v1.1 API复核 | 变化 |
|---|---:|---:|---:|
| flags完全匹配率 | 76.36% | 87.27% | +10.91个百分点 |
| flags Macro-F1 | 79.93% | 94.58% | +14.65个百分点 |
| 多标签完全匹配率 | 46.67% | 60.00% | +13.33个百分点 |
| 派生action准确率 | 90.91% | 89.09% | −1.82个百分点 |
| Invalid Execution Rate | 0.00% | 2.00% | +2.00个百分点 |
| Premature Call Rate | 0.00% | 4.17% | +4.17个百分点 |

逐任务flags转移：

| 转移 | 数量 |
|---|---:|
| 正确→正确 | 40 |
| 正确→错误 | 2 |
| 错误→正确 | 8 |
| 错误→错误 | 5 |

因此，净增加6条完全正确任务，但有2条原本正确的任务在v1.1中退化。

## 5. 各flag变化

| Flag | v1 Recall | v1.1 Recall | 变化 |
|---|---:|---:|---:|
| `missing_parameter` | 91.67% | 83.33% | −8.33个百分点 |
| `ambiguous_parameter` | 66.67% | 66.67% | 0 |
| `contract_defined_out_of_domain` | 86.67% | 93.33% | +6.67个百分点 |
| `contract_defined_unsupported_system` | 16.67% | 100.00% | +83.33个百分点 |
| `unavailable` | 93.33% | 100.00% | +6.67个百分点 |
| `version_mismatch` | 100.00% | 100.00% | 0 |

v1.1最明确的成功是：

```text
unsupported system不再被系统性误写为一般contract OOD
```

主要未解决项是：

```text
ambiguous_parameter Recall仍为66.67%
```

## 6. 七条错误

### 6.1 缺参漏检

`E2P-A001-02`：

```text
expected_flags = [missing_parameter]
predicted_flags = []
expected_action = clarify
derived_action = call
```

这是本轮唯一实际导致提前调用的错误，也是`Invalid Execution Rate = 2%`的来源。

### 6.2 缺参与不可用组合

`E2P-A001-10`遗漏`missing_parameter`，只输出`unavailable`：

```text
expected_action = clarify
derived_action = refuse
```

没有错误调用工具，但没有遵守“先补齐输入”的动作优先级。

### 6.3 歧义与超域组合

以下四条均只保留`contract_defined_out_of_domain`，遗漏`ambiguous_parameter`：

```text
E2P-A001-11
E2P-A002-09
E2P-A003-09
E2P-B019-12
```

结果均为：

```text
expected_action = clarify
derived_action = refuse
```

这说明仅在提示词中声明“保留全部flags”仍不足以稳定解决多标签遮蔽。

### 6.4 超域与不可用组合

`E2P-B019-13`只识别`unavailable`，遗漏契约超域，但两者均派生`refuse`，因此动作仍正确。

## 7. 开发门判断

预先关注的四项开发检查：

| 检查 | 结果 |
|---|---|
| Schema有效率达到100% | 通过 |
| unsupported-system Recall改善 | 通过 |
| 多标签完全匹配率改善 | 通过 |
| clarify动作准确率改善 | **未通过** |

因此最准确的状态是：

```text
v1.1 development recheck = passed_with_limitations
```

不能表述为：

```text
E2边界门控已经通过
CF-04已经通过
v1.1优于v1的确认性结论
```

## 8. 下一研究决策

不建议继续在同一55条任务上进行v1.2、v1.3式提示词反复拟合。当前结果已经足以证明：

1. flags-only职责拆分是正确的工程方向；
2. 纯提示词策略对明确的结构缺失和多标签优先级仍有随机漏检；
3. 结构化请求中的required字段缺失、显式歧义标记、版本错配和服务状态可由程序直接验证；
4. LLM更适合判断需要语义理解的契约适用域和不支持系统。

下一候选方法应作为新的系统条件，而不是继续改写同一提示词：

```text
确定性结构检查
→ missing / ambiguous / unavailable / version flags

LLM契约语义检查
→ contract OOD / unsupported system / model-card OOD

合并全部flags
→ 冻结政策派生状态和动作
```

这与项目的“双层边界门控”主线一致，也能直接检验确定性前置检查是否降低提前调用和多标签遗漏。

## 9. CF-04仍未通过的原因

除当前动作回退外，CF-04仍缺少：

- 温度范围契约；
- 压力范围契约；
- 神经网络模型卡OOD契约；
- 新任务上的独立验证；
- 多次模型重复与波动估计；
- E2正式样本量依据。

因此CF-08和CF-09的E2组件仍不能冻结。

## 10. 自动测试

本轮新增测试验证：

1. API运行55条完整、无供应商失败；
2. 运行manifest全部哈希一致；
3. 运行和分析产物不包含API密钥；
4. v1与v1.1任务集合严格相同；
5. 配对转移同时保留改善和回退；
6. unsupported-system Recall为100%；
7. 动作准确率回退和clarify开发门失败被显式记录；
8. 分析manifest绑定运行包及基线候选包。

完整测试结果：

```text
Core Freeze完整回归：137 passed
```

## 11. 产物

API运行：

```text
outputs/v11_cf04_e2_policy_v1_1_recheck_20260731/
```

配对分析：

```text
outputs/v11_cf04_e2_policy_v1_1_recheck_analysis_20260731/
├── task_errors.csv
├── mutation_comparison.csv
├── flag_comparison.csv
├── comparison_report.json
└── artifact_manifest.json
```

两个包均保存源文件哈希、运行配置、执行授权、逐任务记录和非确认性状态。
