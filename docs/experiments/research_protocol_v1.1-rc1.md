# 面向冶金可执行计算任务的工具调用研究协议 v1.1

## 文档状态

- 版本：`1.1-rc1`
- 日期：2026-07-30
- 状态：协议升级候选版，待工具验证和先导实验
- 适用范围：主论文E1a、E1b、E2、E3
- 前置版本：`research_protocol_v1.0.md`的`1.0-rc3.1`
- Core Frozen：`false`

本协议替换旧协议中依赖专家逐题金标准的确认性路径。未明确替换的版本治理、日志、随机化、数据泄漏和结果报告原则继续适用。

## 1. 研究目标

### 1.1 总目标

面向具有版本化工具契约和可执行参考答案的冶金计算工具环境，研究大语言模型能否：

1. 识别并实现工具调用带来的可测量收益；
2. 在信息不足、输入歧义、超适用域和工具不可用时采取正确动作；
3. 在大规模契约近邻中召回并选择可接受工具；
4. 生成正确参数、合法执行并忠实呈现工具结果。

通俗表述为：

> 有收益时调用，不能调用时停下，可以调用时选对并正确执行。

### 1.2 确认性结论范围

确认性结论限定为：

> 在机器可验证任务、版本化工具契约和当前验证工具集合内的方法表现。

开放式工艺建议、材料选择、故障诊断、高风险工程决策和无客观参考答案的解释性任务不进入确认性主实验。

## 2. 核心概念

### 2.1 已验证工具

`verified_tool`必须同时具备：

- 可追溯公式、数据、模型卡或公开规范；
- 版本化输入输出契约；
- 明确适用域和限制；
- 独立参考实现或公开标准算例；
- 正常、边界、量纲和性质测试；
- 预设数值容差；
- 不依赖被测工具自身输出建立参考真值。

工具状态为：

```text
verified_core
conditionally_verified
unverified
known_defect
```

只有`verified_core`进入E1b确认性计算收益实验。

### 2.2 工具契约

工具契约至少包含：

```yaml
tool_id:
tool_version:
scientific_function:
required_inputs:
optional_inputs:
input_units:
output_contract:
supported_systems:
supported_phases:
temperature_range:
pressure_range:
composition_constraints:
model_assumptions:
data_or_model_version:
validation_rules:
reference_sources:
service_status:
```

### 2.3 可执行参考真值

`executable_reference`是由独立参考实现、权威公式或公开算例生成的预期结果，包含：

```yaml
reference_value:
reference_unit:
tolerance:
reference_version:
reference_source:
oracle_implementation:
```

### 2.4 调用收益

工具调用收益是实验效应：

```text
Accuracy Gain
= E[Correct | Forced Verified Tool]
− E[Correct | No Tool]
```

`tool_benefit`只能在重复运行后派生：

```text
positive
neutral
negative
uncertain
```

它不是单条任务的先验金标签，也不自动等于`required`。

### 2.5 契约定义边界

本研究只声明：

- `contract_defined_out_of_domain`；
- `model_card_defined_ood`；
- `contract_defined_unsupported_system`。

除非有独立外部证据，不将其扩大为普遍科学OOD或真实工业不可用。

### 2.6 契约近邻

契约近邻是依据机器可读工具契约自动生成的干扰工具，包括：

- 词法近邻；
- 输出量近邻；
- 相态近邻；
- 温区近邻；
- 体系近邻；
- 数据或模型版本近邻；
- 不可用近邻。

未经外部确认时，不声称这些近邻代表全部真实冶金功能相似关系。

## 3. 研究问题与假设

### RQ1：工具调用收益与Schema暴露

> 在机器可验证任务中，已验证工具调用能否提高最终正确性、稳定性或可追溯性；Schema暴露是否影响系统识别并实现这种收益？

#### H1a：Schema暴露效应

Blind、Taxonomy和Full Schema将产生不同的调用倾向、无效调用率和端到端结果。Full Schema可能提高部分工具收益任务的调用率，同时增加无收益任务的调用。

#### H1b：验证工具调用收益

在至少部分预注册计算任务家族中，Forced Verified Tool相对于No Tool具有正的准确率、稳定性或可追溯性收益。

H1b不要求所有任务家族均有正收益；无收益和负收益均为有效结果。

### RQ2：执行准备度与边界

> 系统能否在输入不完整、参数歧义、超出契约适用域、体系不支持和服务不可用时采取正确动作？

#### H2：契约边界门控

与Direct FC相比，契约边界门控将降低非ready任务中的真实调用率，同时保持ready任务的合法执行率。

### RQ3：大规模契约路由与可靠执行

> 系统能否在大规模契约近邻中召回并选择可接受工具，生成正确参数，合法执行，并忠实呈现工具结果？

#### H3：规模与契约近邻效应

工具选择性能随工具池规模和契约近邻剂量增加而下降；适用域契约不匹配近邻比单纯词法近邻造成更大的误选风险。

#### H4：层次化路由稳定性

与Full Schema、Lexical Top-5和Dense Top-5相比，Hierarchical Top-5在17至120工具扩展中具有更小的选择性能下降。

## 4. 实验总览

| 实验 | 目的 | 主要指标 |
| --- | --- | --- |
| E1a | Schema暴露是否改变调用行为和结果 | 调用率、最终正确率、Invalid Execution Rate |
| E1b | 验证工具相对No Tool的收益 | Accuracy Gain |
| E2 | 执行准备度与边界门控 | Readiness Macro-F1、Invalid Execution Rate |
| E3 | 大规模召回、选择、参数和执行 | Recall@5、Acceptable Tool Selection Accuracy |

成本、延迟、可追溯性和严格端到端成功率分别报告，不合并为唯一确认性总分。

## 5. E1a：Schema暴露效应

### 5.1 实验条件

```text
Blind
Taxonomy
Full Schema
```

Length-Control可以作为控制条件保留，但是否进入正式比较须在先导实验前固定。

### 5.2 固定输入

同一任务、模型、工具版本、政策、运行配置和参考答案保持一致，只改变可见工具信息。

### 5.3 主要结果

- 调用率；
- 最终答案正确率；
- Invalid Execution Rate；
- 有收益任务上的调用实现率；
- 无收益任务上的额外调用率。

旧`evidence_requirement`三分类结果只作探索性报告，不承担新RQ1的唯一主要结论。

## 6. E1b：调用收益

### 6.1 条件

```text
No Tool
Forced Verified Tool + Oracle Parameters
End-to-End Forced Tool
Autonomous Tool Use
Boundary-Gated Tool Use
```

其中主要因果对比为：

```text
Forced Verified Tool + Oracle Parameters
vs
No Tool
```

该对比隔离“验证工具可用性”的收益。End-to-End条件用于定位路由、参数和结果解释损失。

### 6.2 任务资格

任务必须同时满足：

- 有独立可执行参考答案；
- 数值或结构化结果可自动评分；
- 目标工具状态为`verified_core`；
- 输入位于契约声明适用域；
- 参考容差在观察正式结果前固定。

开放式建议、主观解释和没有参考答案的任务不进入E1b确认性数据。

### 6.3 重复与收益估计

每个条件进行多次独立运行。正式重复次数由先导波动和功效分析确定。

主要效应：

```text
Accuracy Gain
= Accuracy_ForcedVerifiedTool
− Accuracy_NoTool
```

次要效应：

```text
Stability Gain
Traceability Gain
Normalized Error Difference
```

Token、延迟、API费用和重试次数独立报告。

### 6.4 防循环评价

如果使用`tool_benefit`训练、校准或评价门控：

- 收益估计运行与门控评价运行必须分离；或
- 使用预注册交叉拟合；
- 不允许同一运行既产生收益标签又证明门控识别正确。

确认性收益优先按预注册任务家族估计。单任务收益类别只作诊断，除非重复数足以支持预设置信区间。

## 7. E2：执行准备度与边界

### 7.1 底层多标签事实

```yaml
flags:
  - missing_parameter
  - ambiguous_parameter
  - contract_defined_out_of_domain
  - contract_defined_unsupported_system
  - unavailable
  - model_card_defined_ood
```

一条任务允许多个flags。

### 7.2 自动任务变换

从合法基础任务执行单因素或预注册组合变换：

- 删除必需参数；
- 删除单位或引入单位歧义；
- 将数值改到契约范围外；
- 修改相态或材料体系；
- 修改模型或数据版本；
- 切换工具服务状态；
- 将神经网络输入改到模型卡声明范围外。

每次变换记录来源任务、变换类型、规则版本和随机种子。

### 7.3 政策优先级

默认优先级在正式先导前冻结：

```text
风险禁止
> 输入歧义或缺失
> 契约超域或体系不支持
> 工具不可用
> ready
```

高风险状态只在有明确协议规则时进入确认性实验，否则保持探索性。

### 7.4 主要指标

- Readiness Macro-F1；
- flags多标签F1；
- flags Jaccard；
- Action Accuracy；
- Invalid Execution Rate；
- Premature Call Rate；
- Out-of-Domain Call Rate；
- Required Information Coverage；
- Alternative Success Rate。

## 8. E3：大规模契约路由

### 8.1 工具规模

```text
17、50、100、120
```

扩大规模时目标工具、任务文本、参考答案和已有干扰工具保持不变：

```text
Pool-17 ⊂ Pool-50 ⊂ Pool-100 ⊂ Pool-120
```

120工具目录可以由：

```text
verified executable core
+ schema-only routing catalog
```

组成。论文必须分别报告两者数量，不得将Schema-only工具称为已验证计算引擎。

### 8.2 契约近邻剂量

```text
near_neighbor_count = 0、4、8
```

近邻类型包括：

```text
lexical
output
phase
temperature_range
system
version
availability
```

无法从契约自动证明的现实功能近邻不进入确认性近邻对比。

### 8.3 路由方法

- Full Schema；
- Lexical Top-5；
- Dense Top-5；
- Hierarchical Top-5；
- Oracle Top-5。

所有Top-K正式固定为`K=5`，除非在查看正式测试结果前完成协议修订。

### 8.4 分阶段评分

#### 候选召回

- Recall@5；
- Set Recall@5；
- MRR；
- nDCG@5；
- 检索延迟。

#### 工具选择

```text
selected_tool ∈ acceptable_tools
```

报告Acceptable Tool Selection Accuracy及契约误选类型。

#### 参数生成

- Parameter Recall；
- Parameter Value Accuracy；
- Exact Parameter Match。

数值先统一单位再按容差比较；枚举、版本、材料和相态在规范化后比较。

#### 执行

- Execution Success Rate；
- Valid Execution Rate；
- Tool Output Fidelity；
- Final Answer Accuracy。

HTTP或函数返回成功不等于科学有效执行。

### 8.5 可接受工具集合

多个工具只有在以下条件全部满足时才能进入同一`acceptable_tools`集合：

- 输入输出语义一致；
- 单位可标准化；
- 契约适用域覆盖任务；
- 共享验证集结果在预设容差内；
- 数据或模型版本允许等价。

无法自动证明等价时，只保留来源工具为唯一可接受工具，并在限制中说明现实开放性不足。

## 9. 可追溯性和成本

### 9.1 可追溯性

可追溯性使用0—3分的程序化检查：

| 分数 | 条件 |
| ---: | --- |
| 0 | 无来源、无工具版本、无法复核 |
| 1 | 声称使用工具，但缺输入或版本 |
| 2 | 有工具、输入和来源，但证据链不完整 |
| 3 | 输入、工具版本、数据版本和结果均可复现 |

### 9.2 成本

分别记录：

- 输入Token；
- 输出Token；
- Schema Token；
- 检索延迟；
- 工具延迟；
- 模型延迟；
- 端到端延迟；
- API费用；
- 失败重试次数。

成本不与准确率揉成确认性综合分。

## 10. 严格端到端成功

次要指标`Strict End-to-End Success`仅在下列条件全部成立时为1：

```text
调用行为符合实验条件
∧ 准备度动作正确
∧ 正确工具进入候选集
∧ 选择可接受工具
∧ 参数正确
∧ 合法执行成功
∧ 最终答案正确
```

阶段式指标始终优先于该总指标用于错误归因。

## 11. 数据层级

### 11.1 受控确认性集

`controlled_confirmatory`由工具契约和任务生成器构造，用于E1b、E2和E3的受控结论。该层不设置合成任务30%上限，但必须保存来源工具、规则、随机种子和参考执行。

### 11.2 自然表达验证集

`naturalistic_validation`来自公开算例、脱敏真实日志或自然表达改写。只有具有机器可验证真值的任务进入定量结果，其余只作定性分析。

### 11.3 探索性领域案例

`exploratory_domain_cases`包含开放式工艺建议、材料选择、真实复杂故障诊断和高风险决策，不进入确认性准确率。

三层数据必须分别报告。

## 12. 人工质量控制

人工不逐题自由标注确认性标签，只负责：

- 工具来源和版本录入；
- 契约字段录入与软件级复核；
- 单位映射检查；
- 生成器输出语法和可读性抽检；
- 参考执行异常排查；
- 证据文件和哈希管理。

未经外部证据支持的领域判断必须标记为探索性。

## 13. 统计原则

- 正式任务、工具版本、生成器和容差在运行前冻结；
- 任务家族和工具家族作为聚类层级；
- 重复运行不得平铺为独立任务；
- 报告效应量和95%置信区间；
- 任务家族收益使用分层或混合效应模型；
- H3/H4可复用现有GLMM和Bootstrap基础设施，但必须先完成新接口干跑；
- 负收益、无收益和不收敛结果均必须报告；
- 不能根据正式结果更换工具、任务家族、容差或主要指标。

## 14. 外部验证

通用函数调用能力使用公开基准作为外部验证。自建契约任务用于验证冶金计算环境内的受控因果和工程行为。

外部公开基准结果、自建受控结果和自然案例结果分别报告，不能互相替代。

## 15. 冻结前门槛

申请v1.1 Core Frozen前至少完成：

1. 协议和数据规范兼容性审查；
2. 至少3个`verified_core`工具及独立参考实现；
3. 工具契约Schema和自动验证器通过测试；
4. E1b基础任务和重复运行先导；
5. E2单因素变换和多标签规则测试；
6. E3参数规范化、候选集合和契约近邻测试；
7. 17/50/100/120 Schema API可行性检查；
8. 受控、自然和探索数据分层检查；
9. 功效分析和正式重复次数确定；
10. 样本量附录；
11. 新统计接口和报告模板干跑；
12. 所有正式数据、生成器、契约和参考结果哈希冻结。

在以上条件完成前：

```text
core_frozen = false
```

## 16. 研究声明限制

本研究不声称：

- 工具契约覆盖全部真实冶金边界；
- Schema-only目录包含120个已验证计算引擎；
- 契约定义OOD等同于普遍科学OOD；
- 自动等价类等同于专家认可的全部科学等价关系；
- 系统达到冶金专家水平；
- 结果可直接用于高风险工业决策。

任何超出本协议的结论必须作为协议扩展单独注册。
