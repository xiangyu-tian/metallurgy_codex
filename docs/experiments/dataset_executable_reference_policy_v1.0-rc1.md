# 契约驱动与可执行参考数据规范 v1.0

## 文档状态

- 版本：`1.0-rc1`
- 日期：2026-07-30
- 状态：候选版，配套`research_protocol_v1.1-rc1.md`
- Core Frozen：`false`

本规范定义无需专家逐题自由标注的确认性数据生产流程。正式真值只能来自工具契约、任务生成规则、独立可执行参考或外部公开基准。

## 1. 设计原则

1. 先注册和验证工具，再从工具反向生成任务；
2. 任务参数由生成器采样，参数真值不由标注者补写；
3. 准备度和边界标签由契约与变换规则产生；
4. 参考答案由独立执行产生，不能使用被测工具自证；
5. 多标签事实与单一政策动作分离；
6. 受控任务、自然验证任务和探索案例分层；
7. 所有任务可追溯到生成器、随机种子、工具版本和参考执行；
8. AI生成文本只负责表述扩展，不负责生成科学真值。

## 2. 工具契约表

```yaml
tool_id: string
tool_version: string
tool_status: verified_core | conditionally_verified | unverified | known_defect
scientific_family: string
scientific_function: string
required_inputs: []
optional_inputs: []
input_units: {}
output_contract: {}
supported_systems: []
supported_phases: []
temperature_range: object | null
pressure_range: object | null
composition_constraints: []
model_assumptions: []
data_or_model_version: string | null
service_status: available | unavailable
validation_rules: []
reference_sources: []
contract_version: string
contract_hash: string
```

契约只陈述来源文档、公式、模型卡或测试证据明确支持的范围。没有来源的字段不得推测性填写为正式约束。

## 3. 工具验证清单

```yaml
validation_id: string
tool_id: string
tool_version: string
formula_or_model_source: string
independent_oracle: string
normal_case_ids: []
boundary_case_ids: []
dimension_case_ids: []
metamorphic_case_ids: []
tolerance_spec: object
known_limitations: []
validation_status: passed | failed | conditional
validated_at: datetime
evidence_hashes: {}
```

只有`validation_status=passed`且工具状态为`verified_core`的工具可作为E1b确认性Forced Verified Tool。

## 4. 基础任务表

```yaml
task_id: string
task_family_id: string
data_layer: controlled_confirmatory | naturalistic_validation | exploratory_domain_cases
source_tool_id: string | null
source_tool_version: string | null
generator_version: string
random_seed: integer
problem_text: string
canonical_inputs: {}
expected_parameters: {}
acceptable_tools: []
reference_execution_id: string | null
reference_output: object | null
scoring_rule_id: string | null
source_type: contract_generated | public_case | real_log | external_benchmark | exploratory
source_reference: string | null
```

`controlled_confirmatory`任务必须具有`source_tool_id`、`generator_version`、`random_seed`和可执行评分规则。

## 5. 参考执行表

```yaml
reference_execution_id: string
task_id: string
oracle_implementation: string
oracle_version: string
input_snapshot: {}
output_snapshot: {}
output_unit: string | null
tolerance: object
reference_source: string
executed_at: datetime
execution_hash: string
```

参考实现必须独立于被测工具的生产实现。无法满足独立性时，任务不得进入E1b确认性数据。

## 6. 任务变换表

```yaml
mutation_id: string
base_task_id: string
mutated_task_id: string
mutation_type: string
mutation_rule_version: string
changed_fields: {}
expected_flags: []
primary_status: string
allowed_actions: []
policy_expected_action: string | null
random_seed: integer
```

正式变换类型至少包括：

```text
remove_required_parameter
remove_unit
make_unit_ambiguous
out_of_temperature_range
out_of_pressure_range
unsupported_phase
unsupported_system
unavailable_tool
model_card_defined_ood
version_mismatch
```

## 7. 多标签准备度

底层flags允许同时成立：

```text
missing_parameter
ambiguous_parameter
contract_defined_out_of_domain
contract_defined_unsupported_system
unavailable
model_card_defined_ood
version_mismatch
```

不得为了方便评分只保留一个事实。`primary_status`和`policy_expected_action`由版本化优先级程序派生。

默认优先级：

```text
risk_prohibited
> missing_or_ambiguous_input
> contract_out_of_domain_or_unsupported
> unavailable
> ready
```

## 8. 可接受工具集合

基础任务从来源工具反向生成时，默认：

```yaml
acceptable_tools:
  - source_tool_id
```

其他工具只有在自动等价验证通过后才能加入：

```text
输入输出语义一致
∧ 单位可标准化
∧ 适用域覆盖任务
∧ 共享验证集差异不超过预设容差
∧ 数据或模型版本允许等价
```

无法自动证明时保持单一可接受工具，不由非专家主观扩展集合。

## 9. 契约近邻表

```yaml
target_tool_id: string
distractor_tool_id: string
neighbor_type: lexical | output | phase | temperature_range | system | version | availability
contract_evidence: {}
is_acceptable_for_task: boolean
exclusion_reason: string | null
generator_version: string
```

确认性近邻必须能够由契约字段和任务输入自动复算。真实但无法机器验证的专业近邻只进入探索性数据。

## 10. 参数规范化

评分前执行：

- 单位统一；
- 化学式规范化；
- 材料名称映射；
- 相态枚举映射；
- 数据和模型版本标准化；
- 数值容差比较；
- 无序集合排序。

参数指标：

```text
Parameter Recall
Parameter Value Accuracy
Exact Parameter Match
```

不得使用原始JSON字符串完全相等作为唯一评分。

## 11. 结果评分规则

### 11.1 数值正确性

```text
correct = 1
当 |prediction − reference| ≤ tolerance
否则为0
```

同时记录：

```text
Normalized Error
= |prediction − reference|
÷ max(|reference|, epsilon)
```

### 11.2 结构化结果

使用字段级覆盖、值准确率和严格完全匹配。

### 11.3 工具结果忠实度

| 分数 | 定义 |
| ---: | --- |
| 0 | 篡改核心数值、单位或方向 |
| 1 | 核心结果正确但遗漏重要限定 |
| 2 | 数值、单位和条件正确 |
| 3 | 在2分基础上准确说明适用域和不确定度 |

能够程序检查的字段自动评分；需要开放式解释判断的部分不进入确认性主指标。

### 11.4 可追溯性

| 分数 | 定义 |
| ---: | --- |
| 0 | 无来源和版本 |
| 1 | 有工具声明但缺输入或版本 |
| 2 | 工具、输入和来源存在但链条不完整 |
| 3 | 输入、工具版本、数据版本和结果可复现 |

## 12. 调用收益数据

运行结果表必须保存：

```yaml
run_id: string
task_id: string
condition: no_tool | oracle_tool | forced_end_to_end | autonomous | boundary_gated
model_id: string
model_version: string
model_run_repeat: integer
selected_tool: string | null
generated_parameters: object | null
execution_status: string | null
final_answer: object
correct: boolean
normalized_error: number | null
traceability_score: integer
token_usage: object
latency: object
cost: object
```

`tool_benefit`不写回基础任务表，而是在独立分析表中按任务家族、模型和实验条件派生。

## 13. 收益派生与防泄漏

收益派生表：

```yaml
benefit_analysis_id: string
task_family_id: string
model_id: string
forced_tool_accuracy: number
no_tool_accuracy: number
accuracy_gain: number
confidence_interval: []
benefit_class: positive | neutral | negative | uncertain
analysis_split: calibration | evaluation
```

如果门控使用收益类别进行训练或阈值校准：

- `calibration`运行用于估计收益；
- `evaluation`运行用于评价门控；
- 或执行预注册交叉拟合；
- 禁止同一运行同时承担标签生成和性能证明。

## 14. 数据生产流水线

正式流水线固定为：

```text
1. 注册工具
2. 编写工具契约
3. 运行工具验证
4. 从合法输入空间采样基础任务
5. 运行独立参考实现
6. 生成自然语言问题
7. 生成缺失、歧义、超域和不可用变换
8. 插入契约近邻
9. 重新运行规则验证器
10. 生成任务、标签和评分文件
11. 冻结版本、随机种子与哈希
```

任一步失败均不得将对应任务升级为确认性数据。

## 15. 数据层级

### 15.1 `controlled_confirmatory`

- 真值必须机器可验证；
- 允许系统化模板和变换；
- 不设置合成任务30%上限；
- 用于主要因果和边界结论。

### 15.2 `naturalistic_validation`

- 来源为公开算例、脱敏真实日志或自然表达；
- 具有机器真值的任务可进入定量结果；
- 无机器真值的任务只作定性分析。

### 15.3 `exploratory_domain_cases`

- 开放式建议、复杂设计、无真值诊断和高风险决策；
- 不进入确认性准确率和假设检验。

三层不得合并计算一个总体准确率。

## 16. 数据划分

- 同一`task_family_id`全部进入同一划分；
- 同一基础任务的所有变换进入同一划分；
- 同一参考算例的自然语言改写进入同一划分；
- 工具等价验证集与正式任务集分离；
- 收益校准运行与门控评价运行分离；
- 正式测试任务不得用于提示词、阈值、检索权重或容差调参。

## 17. 自动质量检查

至少检查：

- 契约Schema有效；
- 所有来源工具存在；
- `verified_core`具有通过的验证记录；
- 参考执行存在且哈希匹配；
- 变换后的flags可由规则复算；
- `acceptable_tools`非空；
- 参数和输出单位可规范化；
- 容差为有限非负数；
- 任务家族划分无泄漏；
- 运行结果没有回写基础真值；
- AI生成文本没有修改canonical inputs；
- API密钥和敏感数据未进入产物。

## 18. 人工抽样质量控制

当前项目人员可以检查：

- 问题文本是否通顺；
- 参数是否在文本中正确呈现；
- 单位和字段映射是否一致；
- 来源和版本是否完整；
- 生成器是否忠实执行契约；
- 软件输出是否存在明显结构错误。

人工不得将无来源的专业判断升级为确认性标签。

## 19. 冻结条件

本规范升级为冻结版前必须完成：

1. 工具契约Schema和验证器测试；
2. 至少3个`verified_core`工具；
3. 独立参考执行测试；
4. 基础任务与变换任务生成测试；
5. 参数规范化和评分测试；
6. 收益校准/评价隔离测试；
7. 数据分层和划分泄漏测试；
8. 小规模先导和功效分析；
9. 文件清单、版本和哈希记录；
10. 报告模板干跑。

在全部完成前：

```text
status = rc
core_frozen = false
```
