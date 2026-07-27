# 冶金工具调用数据集2.0标注与政策规范 v1.0

## 文档状态

- 版本：`1.0-rc3`
- 日期：2026-07-27
- 状态：候选冻结版，待冶金专家与计算机方向成员联合审查
- 关联协议：`docs/experiments/research_protocol_v1.0.md`
- 适用对象：数据设计者、标注者、裁决专家、评测实现者

本规范定义数据集2.0的任务结构、标签语义、动作政策、标注流程、数据划分和质量审计规则。任何评测代码不得自行推断或改变本文定义的标签含义。

---

## 1. 设计原则

### 1.1 三个问题分开标注

每条任务必须区分：

1. 是否需要外部专业计算证据；
2. 当前信息和平台能力是否允许执行；
3. 若允许执行，应选择哪个工具以及如何执行。

不得仅使用`should_call_tool`一个二元字段表达全部问题。

### 1.2 能力合理性与平台政策分开

- `allowed_actions`表示科学和交互上可以接受的动作集合；
- 政策派生表中的`policy_expected_action`表示特定平台政策下要求执行的单一动作。

能力测试按集合评分，政策测试按单一动作评分。
`policy_mode`不属于任务科学标签；同一个`task_id`可以关联多个政策记录，不复制科学任务。

### 1.3 底层状态允许多标签

同一任务可以同时存在：

- 信息不足；
- 超出适用域；
- 能力不可用；
- 高风险。

底层事实使用`boundary_flags`完整保留；最终动作由政策矩阵和优先规则产生。

### 1.4 最小差异组优先

研究调用边界时，优先构造只改变一个条件的最小差异问题组，例如只改变：

- 是否要求具体数值；
- 是否指定数据标准；
- 是否要求可追溯；
- 是否缺少关键参数；
- 是否超适用域；
- 是否处于高风险决策场景。

### 1.5 不以关键词替代科学判断

“计算”“数值”“模型”“验证”等词不能单独决定是否调用；标注必须依据证据需求、任务复杂度、数据依赖、风险和可复现性。

---

## 2. 数据组织

数据集2.0由公共任务表和四个Track扩展表组成。

### 2.1 公共任务表

```yaml
task_id: string
dataset_version: string
track_membership: [A, B, C, D]
domain: string
subdomain: string
scientific_system: string
source_type: expert | public_case | real_log | synthetic
source_reference: string | null
problem_text: string
context: string | null
language: zh | en | mixed
minimal_pair_group: string | null
template_group: string | null
difficulty: easy | medium | hard
difficulty_score: 0 | 1 | 2 | 3 | 4 | 5
construction_flags: []
split: train | dev | test | generalization
annotation_status: draft | double_annotated | adjudicated | audited
legacy_case_id: string | null
created_at: datetime
updated_at: datetime
```

### 2.2 Track关系

- 一条任务可以属于多个Track；
- Track A无工具任务不必填写Track C、D字段；
- Track B路由任务可以不执行真实工具；
- Track C、D必须引用公共`task_id`；
- 不允许为填满字段而生成无意义的空标签。

### 2.3 难度的操作性定义

以下条件每满足一项计1分：

1. 需要识别三个及以上科学条件；
2. 存在三个及以上可接受工具或高相似度近邻；
3. 必须区分具体科学适用域；
4. 需要多步骤依赖推理；
5. 含歧义、对抗诱导或冲突要求。

映射规则：

```text
0—1分：easy
2—3分：medium
4—5分：hard
```

人工覆盖难度等级必须保存覆盖理由。

---

## 3. Track A：调用边界集

### 3.1 字段

```yaml
task_id: string
evidence_requirement: none | optional | required
answerability: answerable | ambiguous_request | missing_task_information
information_status: sufficient | missing_execution_input | ambiguous_execution_input
capability_status: available | unavailable | uncertain
risk_status: normal | review_required
boundary_flags: []
allowed_actions: []
required_inputs: []
missing_inputs: []
coarse_capability: string | null
action_reason: string
annotation_confidence: high | medium | low
disagreement_notes: string | null
```

### 3.2 `evidence_requirement`

#### `none`

可靠回答不需要外部专业计算证据，典型任务包括：

- 概念和定义；
- 不依赖具体工况的原理说明；
- 已给结果的语言解释；
- 不要求数值结论的方法介绍。

反例：虽然问题文字简短，但要求具体热力学、动力学或工程数值时，不能标为`none`。

#### `optional`

直接推导和工具调用均可能合理，典型特征：

- 公式封闭；
- 使用稳定公开常数；
- 一步或少量简单运算；
- 过程可在回答中完整展示；
- 风险低；
- 用户没有指定审计、标准版本或工程用途。

例如普通问答中的Fe₂O₃近似摩尔质量。

如果用户要求指定数据标准、精度、来源、可追溯记录或工程使用，则应重新判断为`required`，而不是继续标记为`optional`。

#### `required`

满足以下任一情况通常标为`required`：

- 依赖专业数据库或特定数据版本；
- 依赖热力学、动力学、传热、凝固、物料衡算等专业模型；
- 需要多步骤计算或迭代求解；
- 输入和结果必须形成可审计证据链；
- 结果用于科研复现、工程决策或高风险操作；
- 大模型无法在回答中完整、透明、可靠地复核全过程。

### 3.3 `answerability`

该字段判断问题本身是否足以产生有意义响应，不涉及具体工具参数。

#### `answerable`

对象、目标和语义完整，可以直接回答、判断是否调用或进入后续门控。

#### `ambiguous_request`

存在多个合理意图或对象，需要用户选择。例如“分析这个氧化铁”可能指FeO、Fe₂O₃或Fe₃O₄。

#### `missing_task_information`

缺少问题对象、指代或任务目标，即使不调用工具也无法可靠回答。例如“解释这个反应为什么发生”，但上下文中没有反应。

### 3.4 `information_status`

该字段只描述粗粒度工具执行所需信息，不等同于问题可回答性。

#### `sufficient`

从一级能力角度看，执行所需的基本科学对象和工况已经给出。它不代表某个具体工具一定适用。

#### `missing_execution_input`

问题可以具有明确语义，但工具执行明显缺少必要工况。例如可以解释算法原理，但没有给出运行算法需要的温度、成分或边界条件。

#### `ambiguous_execution_input`

提供了执行输入，但单位、相态、材料身份或条件解释存在歧义，需要确认后才能安全调用。

### 3.5 `capability_status`

- `available`：冻结的一级能力目录中存在对应能力；
- `unavailable`：对应一级能力明确不存在；
- `uncertain`：仅凭粗粒度能力目录无法确定，需要检索或人工确认。

不得因为大模型可以编造近似答案而把不存在的能力标为`available`。

### 3.6 `risk_status`

- `normal`：不触发额外人工审核；
- `review_required`：涉及高风险工程调整、安全临界条件、受控工艺或可能造成显著现实损失。

### 3.7 `boundary_flags`

允许值包括：

```text
missing_object
missing_parameter
missing_task_info
missing_execution_info
ambiguous_material
ambiguous_phase
ambiguous_condition
capability_unavailable
tool_unavailable
out_of_domain
unsupported_system
unsupported_phase
unsupported_database
high_risk
permission_required
conflicting_requirements
```

可以同时选择多个值。不得为了方便评分只保留一个主状态。

---

## 4. Track B：工具路由集

### 4.1 Track B任务金标准表

```yaml
task_id: string
target_tool_family: string
acceptable_tools: []
unacceptable_near_neighbors: []
routing_reason: string
```

金标准表只存放与任务科学语义有关、不会随方法和随机工具池改变的字段。

### 4.2 工具池元数据表

```yaml
tool_pool_id: string
pool_family_id: string
tool_pool_size: 17 | 50 | 100 | 120
random_seed: integer
tool_ids: []
pool_design: controlled_dose | pure_type_exploratory | mixed_realistic
near_neighbor_type: none | lexical | functional_overlap | mixed
near_neighbor_count: integer
near_neighbor_ratio: number
distractor_composition: object
similarity_distribution: object
schema_token_count: integer
tool_order: []
tool_order_hash: string
construction_status: draft | audited | frozen
```

工具池表记录实验条件，不复制任务科学标签。一个`task_id`通过关联表绑定多个`tool_pool_id`。

### 4.3 实验运行结果表

以下字段属于实验结果，不进入标注金标准：

```yaml
run_id: string
task_id: string
tool_pool_id: string
method: string
retrieved_tools: []
target_rank: integer | null
selected_tool: string | null
predicted_action: string
retrieval_latency_ms: number
model_latency_ms: number
model_resource_time_ms: number
end_to_end_latency_ms: number
token_usage: object
```

`target_rank`只能出现在运行结果中，因为它取决于具体检索方法。不得把运行结果回写并覆盖任务金标准或工具池元数据。

### 4.4 `acceptable_tools`

包含在当前任务、当前输入和当前适用域下科学上可接受的工具集合。多个工具都能正确完成任务时必须全部记录。

不得因为项目希望测试某一个工具，就排除科学上等价的工具。

### 4.5 `unacceptable_near_neighbors`

记录功能相似但在当前条件下不可使用的工具，并说明原因：

```yaml
- tool_id: string
  exclusion_reason: temperature | pressure | composition | phase | system | database | assumption | precision
```

该字段用于研究“功能重叠但适用域不同”的专业混淆。

### 4.6 干扰工具类型与工具池

#### `irrelevant`

与目标工具属于不同一级能力和不同科学对象。

#### `lexical`

名称或描述共享关键词，但科学功能不同。

#### `functional_overlap`

功能相近，但适用体系、相态、温压范围、成分、数据库、模型假设或精度不同，不能在当前任务中互换。

正式池设计：

```text
controlled_dose
pure_type_exploratory
mixed_realistic
```

- `controlled_dose`：近邻类型为`lexical`或`functional_overlap`，近邻数量固定为0、4、8，其余位置由同一无关干扰基底补齐；
- `pure_type_exploratory`：仅用于17、50或真实近邻上限内的小规模控制，不承担17→120主结论；
- `mixed_realistic`：按通过审核的真实工具库比例混合三类干扰，用于外部有效性验证。

### 4.7 嵌套工具池

每个目标任务必须构造：

```text
17 ⊂ 50 ⊂ 100 ⊂ 120
```

每个规模至少有A—E五套预注册工具池。扩大规模时不得替换目标工具或删除已有干扰工具。

正式实验单元为：

```text
task_id
× tool_pool_size
× pool_design
× near_neighbor_type
× near_neighbor_count
× pool_repeat(A—E)
× model_run_repeat
```

某个目标工具缺少足够高相似度近邻时：

- 不得用无关工具补充并标为高相似度；
- 该目标不进入无法满足的确认性剂量条件；
- 只有同时具有至少8个词法近邻和8个功能近邻的目标，才进入两类近邻的确认性配对比较；
- 可以进入`mixed_realistic`池；
- 在工具池元数据中记录缺失原因；
- 使用不平衡设计和混合效应模型处理。

### 4.8 相似度评分表

目标工具与干扰工具分别判断：

1. 是否属于同一一级领域；
2. 是否具有相同科学目标；
3. 是否处理相同输入对象；
4. 是否输出相同物理量；
5. 适用域是否重叠；
6. 仅凭名称是否难以区分。

每项`是=1`、`否=0`，形成0—6分辅助分数：

```text
0—1：low
2—3：medium
4—6：high
```

`functional_overlap`除总分外，还必须满足“科学目标或输出量相同，但当前任务因适用域差异不可互换”。相似度标签由两名标注者独立完成并报告一致性，辅助分数不能替代冶金专家的功能判断。

---

## 5. Track C：多工具编排集

### 5.1 字段

```yaml
task_id: string
required_capabilities: []
acceptable_tools: {}
dependency_graph:
  nodes: []
  edges: []
intermediate_variables: []
required_milestones: []
forbidden_events: []
terminal_conditions: []
allowed_recovery_actions: []
```

### 5.2 依赖图

使用有向无环图表达真正的数据依赖，不保存唯一标准调用序列。

示例：

```yaml
dependency_graph:
  nodes:
    - parse_formula
    - molar_mass
    - material_balance
    - normalize_composition
  edges:
    - [parse_formula, molar_mass]
    - [molar_mass, material_balance]
    - [normalize_composition, material_balance]
```

如果两个节点之间没有边，则允许在满足输入条件的前提下交换顺序或并行执行。

### 5.3 必需里程碑

`required_milestones`描述成功轨迹必须达到的科学状态，而不仅是函数名，例如：

```text
reaction_parsed
temperature_normalized
thermodynamic_result_obtained
mass_balance_closed
final_result_supported
```

### 5.4 禁止事件

`forbidden_events`包括：

- 缺少参数时虚构后调用；
- 超适用域调用；
- 使用未经验证的中间值；
- 完全相同参数重复调用；
- 将失败结果表述为成功；
- 修改或篡改工具返回值；
- 在高风险审核前执行受控动作。

### 5.5 终止条件

`terminal_conditions`描述任务成功状态。轨迹只要满足：

- 必需能力覆盖；
- 依赖无违反；
- 无禁止事件；
- 终止条件满足；

即可视为有效，不要求与某一条固定序列完全一致。

---

## 6. Track D：结果验证集

### 6.1 字段

```yaml
task_id: string
parameter_constraints: []
unit_rules: []
applicability_rules: []
physical_rules: []
numeric_tolerance: object | null
reference_result: object | null
reference_source: string
reference_version: string | null
validation_expected: pass | reject | clarify | escalate
```

### 6.2 验证类型

- 参数类型和格式；
- 必填参数；
- 单位和量纲；
- 数值范围；
- 温度、压力和成分适用域；
- 物质体系和相态；
- 数据库和模型假设；
- 质量、元素和能量守恒；
- 单调性、非负性、边界条件等物理规律；
- 数值容差；
- 结果来源和版本。

验证规则必须尽可能可执行，不得只写“结果应合理”。

---

## 7. 工具级准备度

工具级准备度使用独立关联表`task_tool_readiness`，主键为：

```text
task_id + tool_id + tool_version
```

字段为：

```yaml
task_id: string
tool_id: string
tool_version: string
status: ready | missing_parameter | out_of_domain | unsupported_system | unavailable
missing_parameters: []
violated_constraints: []
alternative_tools: []
decision_reason: string
```

一条任务可以关联可接受工具、近邻工具和替代工具的不同准备度。发布JSON时可以导出为列表，但数据库金标准不得只保存为不可查询的嵌套JSON，也不得用一个单值代表整个候选集。

### 7.1 `ready`

所有必要参数可从用户输入或已验证的前置结果获得，且输入处于具体工具适用域。

### 7.2 `missing_parameter`

候选工具需要的参数无法从用户问题或前置结果中获得，并且不能安全推断。

### 7.3 `out_of_domain`

输入明确违反工具的温度、压力、成分、相态、体系、数据库或模型假设。

### 7.4 `unsupported_system`

工具不支持目标物质体系、工艺、物相或求解目标。

### 7.5 `unavailable`

工具存在于能力目录或元数据中，但当前版本不可执行、权限不足或服务不可用。

---

## 8. 动作集合与政策矩阵

### 8.1 科学标签与政策派生分表

Track A科学标签只保存一次。政策动作保存在独立派生表：

```yaml
task_id: string
policy_mode: capability | conversational | reproducible_research | engineering
policy_expected_action: answer | call | clarify | refuse | escalate | null
policy_version: string
generated_at: datetime
override_reason: string | null
original_generated_action: string | null
approver: string | null
```

同一个`task_id`可以对应四条政策记录，但仍只计为一个唯一语义任务。禁止为不同政策复制公共任务和科学标签。

### 8.2 能力模式

`policy_mode=capability`时：

- `policy_expected_action=null`；
- 只评价预测动作是否属于`allowed_actions`；
- `optional + answerable`通常允许`answer`和`call`；
- 专家可以增加多个合理动作，但必须写明理由。

能力动作基准矩阵：

| 科学状态 | 默认`allowed_actions` |
|---|---|
| `risk_status=review_required` | `[escalate]` |
| `ambiguous_request`或`missing_task_information`且风险普通 | `[clarify]` |
| `none + answerable` | `[answer]` |
| `optional + answerable + sufficient + available/uncertain` | `[answer, call]` |
| `optional + answerable + missing/ambiguous执行信息` | `[answer, clarify]` |
| `optional + answerable + capability unavailable` | `[answer]` |
| `required + answerable + sufficient + available/uncertain` | `[call]` |
| `required + missing/ambiguous执行信息` | `[clarify]` |
| `required + capability unavailable` | `[refuse]` |
| 工具级明确超适用域且无替代工具 | `[refuse]` |

矩阵用于提高双人标注一致性。专家可以覆盖默认集合，但必须记录原集合、覆盖集合和科学理由。`capability_status=uncertain`时的`call`表示允许进入候选检索，不表示已经执行具体工具。

### 8.3 平台政策模式

| 可回答性/证据需求 | 执行信息/能力 | 风险 | conversational | reproducible_research | engineering |
|---|---|---|---|---|---|
| ambiguous_request或missing_task_information | 任意 | normal | clarify | clarify | clarify |
| answerable + none | 任意 | normal | answer | answer | answer |
| answerable + optional | sufficient + available或uncertain | normal | answer | call | call |
| answerable + optional | missing/ambiguous执行信息 | normal | answer | clarify | clarify |
| answerable + optional | capability unavailable | normal | answer | refuse | refuse |
| answerable + required | sufficient + available或uncertain | normal | call | call | call |
| answerable + required | missing/ambiguous执行信息 | normal | clarify | clarify | clarify |
| answerable + required | capability unavailable | normal | refuse | refuse | refuse |
| optional/required | 工具级明确超适用域且无替代工具 | normal | refuse | refuse | refuse |
| answerable的optional/required任务 | 任意 | review_required | escalate | escalate | escalate |

能力测试中的`allowed_actions`仍独立存在。例如`optional + answerable`可以允许`[answer, call]`，即使科研政策要求`call`。

### 8.4 政策动作生成

`policy_expected_action`由版本化规则程序批量生成，不由标注者逐条自由填写。人工覆盖必须记录：

```text
override_reason
original_generated_action
overridden_action
approver
```

---

## 9. 多状态冲突与动作优先级

### 9.1 底层事实

所有成立的状态均写入`boundary_flags`，例如：

```yaml
boundary_flags:
  - missing_parameter
  - out_of_domain
  - high_risk
```

### 9.2 默认政策优先级

生成单一政策动作时使用：

```text
高风险审核
> 问题语义不可回答
> 能力或工具不可用
> 明确超适用域
> 缺少或歧义的执行信息
> 条件完备
```

对应动作：

```text
review_required → escalate
ambiguous_request/missing_task_information → clarify
capability/tool_unavailable且证据为optional或required → refuse
out_of_domain → refuse
missing_execution_input/ambiguous_execution_input → 根据evidence_requirement和policy_mode决定
sufficient → 根据evidence_requirement和policy_mode决定
```

如果存在已注册且适用的替代工具，则不标记为最终能力不可用；应在`alternative_tools`中记录，并继续执行替代工具的准备度检查。

### 9.3 例外

如果缺失参数本身决定是否越界，尚不能确认`out_of_domain`，应标记：

```text
missing_parameter
```

并选择`clarify`，不能提前标记明确越界。

---

## 10. 高风险任务

满足以下任一条件可标记`high_risk`：

- 直接用于生产设备设定或自动控制；
- 涉及安全临界温度、压力、成分或负荷；
- 错误可能造成设备损坏、人员风险或显著经济损失；
- 涉及受监管排放、质量放行或合规结论；
- 用户要求绕过人工审核或安全约束；
- 结果超出模型验证范围但仍要求给出确定操作指令。

普通教学算例和明确标注为离线模拟的任务不因涉及高温、高压词语自动判为高风险。

---

## 11. 最小差异问题组

### 11.1 构造规则

一个问题组至少包含两个仅改变一个研究因素的任务。可控制的因素包括：

- 输出从概念解释变为数值；
- 从近似值变为指定标准和精度；
- 从普通问答变为科研复现或工程决策；
- 增加或删除一个必要参数；
- 将输入从适用域内改为适用域外；
- 将工具从可用改为不可用；
- 增加误导数值或工具绕过指令；
- 改变相态、体系或数据库要求。

### 11.2 Fe₂O₃示例

| 问题 | 证据需求 | 可回答性 | 执行信息 | 能力合法动作 |
|---|---|---|---|---|
| 什么是摩尔质量？ | none | answerable | sufficient | answer |
| Fe₂O₃的摩尔质量大约是多少？ | optional | answerable | sufficient | answer/call |
| 使用IUPAC 2021原子量计算Fe₂O₃摩尔质量，保留四位小数并记录来源。 | required | answerable | sufficient | call |
| 计算某种氧化铁的摩尔质量。 | required | ambiguous_request | ambiguous_execution_input | clarify |
| 将Fe₂O₃摩尔质量作为正式物料衡算输入并保存审计记录。 | required | answerable | sufficient | call |
| 解释摩尔质量概念，Fe₂O₃=0只是干扰信息。 | none | answerable | sufficient | answer |

示例结构：

```yaml
task_id: BOUNDARY-MOLAR-002
minimal_pair_group: MPG-MOLAR-MASS-001
problem_text: Fe₂O₃的摩尔质量大约是多少？
evidence_requirement: optional
answerability: answerable
information_status: sufficient
capability_status: available
risk_status: normal
boundary_flags: []
allowed_actions: [answer, call]
action_reason: 公式封闭、常数稳定、过程可透明复核；工具可提高来源一致性。
```

对应政策动作另存于派生表：

```yaml
- task_id: BOUNDARY-MOLAR-002
  policy_mode: conversational
  policy_expected_action: answer
  policy_version: policy-1.0
- task_id: BOUNDARY-MOLAR-002
  policy_mode: reproducible_research
  policy_expected_action: call
  policy_version: policy-1.0
```

### 11.3 划分要求

同一`minimal_pair_group`的全部样本必须进入同一数据划分。

---

## 12. Taxonomy信息泄漏控制

正式能力目录必须：

- 只使用协议定义的一级能力类别；
- 固定内容、顺序、层级和描述长度；
- 所有实验使用同一版本；
- 不因测试问题动态删减目录；
- 明确是否展示当前不可用能力。

人工审计必须确认不存在：

- 具体工具名或ID；
- 参数名；
- 公式名；
- 具体物质或反应；
- 温度、压力、成分范围；
- 数据库版本；
- 候选数量；
- 暗示目标工具的独特短语。

审计结果记录：

```yaml
taxonomy_version: string
reviewers: []
leakage_found: false
issues: []
approved_at: datetime
```

---

## 13. 工具适用域标注

每个正式工具必须提供版本化工具卡：

```yaml
tool_id: string
tool_version: string
scientific_family: string
supported_systems: []
supported_phases: []
temperature_range: object | null
pressure_range: object | null
composition_constraints: []
required_database: string | null
model_assumptions: []
required_inputs: []
optional_inputs: []
output_contract: object
validation_rules: []
reference_sources: []
normalized_tool_name: string
name_identifiability_score: integer
```

标注者先判断任务科学条件，再与工具卡逐项核对。不得只根据工具名称判断适用性。

工具名称必须：

- 使用真实、稳定、规范化的科学语义名称；
- 在Full Schema、Lexical、Dense、Hierarchical和Oracle条件中完全一致；
- 不直接复制测试问题中的完整目标短语；
- 不添加只对某一数据集有效的答案提示；
- 与描述分别进行可辨识度审计。

---

## 14. 数据来源与比例

### 14.1 来源类型

- `expert`：冶金专家直接编写；
- `public_case`：教材、标准、论文或公开算例改写；
- `real_log`：平台真实问题脱敏改写；
- `synthetic`：模板或生成模型扩展。

### 14.2 正式比例约束

- `synthetic`不超过正式数据的30%；
- `expert + public_case + real_log`合计不低于70%；
- 每个核心Track必须包含自然表达问题；
- 不允许使用自动生成样本单独证明外部有效性。

`minimal_pair`和`adversarial`属于构造标记，可以叠加在任一来源上，不与来源比例互斥。

所有来源比例均按唯一语义`task_id`计算。同一任务展开为多种政策、工具规模、工具池、提示条件或模型重复时，仍只计一次；不得用实验条件展开数量膨胀某一来源占比。

### 14.3 来源可追溯

公开算例记录引用和改写方式；真实日志完成脱敏并记录授权状态；不得将含个人或企业敏感信息的原始日志纳入仓库。

---

## 15. 标注流程

### 15.1 角色

- 标注者A：独立标注全部字段；
- 标注者B：不知道A结果，独立标注；
- 裁决专家：处理分歧；
- 质量审计者：检查一致性、政策计算和数据泄漏。

每条正式样本必须双人独立标注。

### 15.2 标注顺序

1. 阅读问题和来源，不看模型输出；
2. 标注证据需求；
3. 分别标注可回答性、执行信息、能力和风险四个轴；
4. 标注全部边界Flags；
5. 生成能力合法动作集合；
6. 将科学标签入Track A，不复制政策任务；
7. 通过政策程序批量生成独立政策派生表；
8. Track B任务再核对可接受工具和近邻工具；
9. 独立构造工具池元数据，不写入运行结果；
10. Track C任务构建依赖图；
11. Track D任务编写可执行验证规则；
12. 双标比较和专家裁决；
13. 自动一致性检查；
14. 版本化入库。

禁止根据某个大模型是否答对来反向修改标签。

### 15.3 分歧记录

裁决时保留：

```yaml
annotator_a:
annotator_b:
disputed_fields: []
disagreement_type:
adjudicated_value:
adjudication_reason:
adjudicator:
```

---

## 16. 一致性测量

至少报告：

- `evidence_requirement`：Cohen's kappa；
- `answerability`：Cohen's kappa；
- `information_status`：Cohen's kappa；
- `capability_status`：Cohen's kappa；
- `risk_status`：Cohen's kappa；
- `boundary_flags`：集合Jaccard和多标签F1；
- `allowed_actions`：集合完全一致率和Jaccard；
- `acceptable_tools`：集合完全一致率和Jaccard；
- 工具相似度等级：加权kappa；
- 政策动作：生成前后完全一致率。

候选冻结门槛：

- 核心单标签字段`κ ≥ 0.75`；
- 集合字段平均Jaccard不低于`0.80`；
- 任一关键类别的原始一致率不低于`0.70`；
- 未达到门槛时必须修订指南并重新标注受影响样本。

一致性统计在专家裁决前计算，不能用裁决后的100%一致代替真实标注一致性。

---

## 17. 数据划分与泛化测试

### 17.1 常规划分

按以下组整体划分：

- 最小差异问题组；
- 模板组；
- 基础算例；
- 真实日志事件。

同组变体不得跨训练、开发和测试集。

### 17.2 独立泛化切分

- `unseen_expression`：未见语言表达；
- `unseen_tool`：未见具体工具，但工具家族已见；
- `unseen_family`：未见工具家族；
- `unseen_system`：未见冶金物质或工艺体系。

不同泛化切分分别报告，不合并为单一平均分。

### 17.3 路由池隔离

开发集用于确定词法表、向量模型、层次和Top-K；正式测试池的目标任务和干扰池不得用于新增别名、调整工具描述或修改相似度标签。

---

## 18. 现有120例迁移规则

现有数据集`1.2.0`保留不变，作为工程回归集。迁移到2.0时：

1. 创建新的`task_id`并保留`legacy_case_id`；
2. 不覆盖旧JSON；
3. 将`should_call_tool`拆解为证据需求、可回答性、执行信息、能力状态、风险状态和合法动作；
4. 重新审查所有简单数值计算；
5. 重新审查`acceptable_actions`与路径要求的冲突；
6. 将信息不足和适用域外样本改为边界Flags；
7. 将多工具固定序列转换为依赖图；
8. 将模型代码转换为可接受工具集合，并将运行排名从金标准中移除；
9. 将政策模式和政策动作迁移到独立派生表；
10. 补充来源、参考版本和适用域；
11. 由两名标注者重新独立标注，不直接继承旧结论。

### 18.1 优先审计样本

- 摩尔质量、单位换算等低复杂度数值任务；
- 含“计算”但实际为概念解释的任务；
- 缺少温度、压力、成分、相态或反应式的任务；
- 超适用域任务；
- 多个工具功能相近的任务；
- 当前`should_call_tool=true`但允许`direct_answer`的任务；
- 所有多工具任务。

---

## 19. 工具独立计数审核

只有满足以下条件的对象才进入120工具正式清单：

1. 独立可执行入口；
2. 独立科学能力；
3. 独立输入输出契约；
4. 明确适用范围；
5. 正常测试和边界测试；
6. 不是仅修改名称或参数配置；
7. 版本差异不重复计数；
8. 不是无独立科学语义的包装层。

每个工具记录：

```yaml
count_status: accepted | merged_as_version | rejected_wrapper | rejected_duplicate | incomplete
computer_reviewer:
metallurgy_reviewer:
decision_reason:
```

---

## 20. 版本管理

版本号使用：

```text
主版本.次版本.修订版本
```

- 标签语义、政策矩阵或测试集变化：主版本；
- 新增样本或工具池但语义不变：次版本；
- 修正错字、引用或不影响标签的元数据：修订版本。

每个版本必须记录：

```yaml
version:
date:
changed_tasks: []
changed_fields: []
reason:
whether_model_results_were_seen:
approvers: []
```

正式测试结果生成后，不得静默修改测试标签。修改后的结果必须使用新版本重新报告。

---

## 21. 自动一致性检查

数据发布前至少检查：

- `allowed_actions`非空；
- 科学任务表不含`policy_mode`和`policy_expected_action`；
- 政策派生表的`policy_expected_action`符合政策矩阵；
- `ambiguous_request/missing_task_information`生成`clarify`；
- `required + sufficient + available + normal`不生成`answer`政策动作；
- `none + answerable + normal`不生成`call`政策动作；
- `required + missing_execution_input`不生成`call`；
- `review_required`工程模式生成`escalate`；
- `acceptable_tools`属于对应工具池；
- 目标工具存在于所有适用工具池；
- `controlled_dose`和`mixed_realistic`的17/50/100/120池满足包含关系；
- `controlled_dose`的近邻数量只能为0、4、8，剩余位置来自登记的无关干扰基底；
- `pure_type_exploratory`记录真实近邻上限，不强制达到100或120；
- Track B金标准不含`target_rank`、Token和延迟；
- 工具池表不含任何模型预测结果；
- 运行结果表不覆盖金标准和工具池元数据；
- `dependency_graph`无环；
- 每个依赖节点有能力或工具映射；
- 每个验证规则可执行或明确标记为专家复核；
- 测试集问题组不出现在开发集；
- 来源比例满足要求；
- 工具计数审核状态为`accepted`。

---

## 22. 质量审计清单

### 22.1 Track A

- 证据需求是否与工具可用性解耦；
- `optional`是否允许多个合理动作；
- 是否错误地按“计算”关键词标注；
- 问题不可回答与工具执行缺参数是否已经分开；
- 可回答性、执行信息、能力和风险是否分别标注；
- 高风险是否有明确现实依据；
- 政策动作是否由矩阵生成。

### 22.2 Track B

- 目标工具是否科学上正确；
- 是否遗漏等价工具；
- 高相似度干扰是否确实不可替代；
- 控制剂量池、探索性纯类型池与现实混合池是否分开；
- 0/4/8近邻剂量是否使用同一无关干扰基底补齐；
- 工具池是否嵌套；
- Schema长度、顺序和位置是否受控；
- 金标准、工具池元数据和运行结果是否分表；
- 工具级准备度是否覆盖每个候选工具；
- 测试池是否被用于调词法或工具描述。

### 22.3 Track C

- 是否错误限定唯一序列；
- 依赖边是否代表真实数据依赖；
- 里程碑是否是科学状态；
- 禁止事件是否可检测；
- 终止条件是否足以定义成功。

### 22.4 Track D

- 适用域是否有来源；
- 单位和量纲是否明确；
- 物理规则是否可运行；
- 数值容差是否合理；
- 参考结果是否可复现；
- 数据库和工具版本是否记录。

---

## 23. 两级冻结条件

### 23.1 Core Frozen

本规范的主论文核心由`1.0-rc3`改为`1.0-core-frozen`前，必须完成：

- Track A、Track B及政策派生表联合审查；
- 至少20个Track A样例双人试标；
- 至少20个Track B样例、0/4/8控制剂量池、探索性纯类型池和现实混合池审查；
- 政策动作生成器通过自动测试；
- Taxonomy人工泄漏审计；
- 标注一致性达到候选门槛；
- 现有120例首轮迁移审计；
- 120工具独立计数初审；
- 17/50/100/120 Full Schema API可行性检查；
- Track B金标准、工具池和运行结果分表检查；
- 数据划分和来源比例确认；
- 样本量附录明确各标签和工具池条件的最低样本量；
- 数据版本清单和质量检查脚本接口确认。

Core Frozen前不得使用正式测试结果修改标签定义或政策矩阵。

### 23.2 Extension RC/Frozen

Track C和Track D保持`extension-rc`，不阻塞RQ1—RQ3。扩展冻结另需：

- 至少5个Track C依赖图审查；
- 至少10个Track D可执行规则审查；
- 轨迹和物理验证评分接口确认；
- Extension数据泄漏与一致性审计。
