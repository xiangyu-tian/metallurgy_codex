# CF-05 E3 A004 难例 R2/R3 重复波动开启包

日期：2026-08-10  
状态：`prepared_local_gate_passed_pending_external_authorization`

## 为什么重复

A004难例R1在48个单元中出现一个严格评分失败：

```text
E1B2-A004-008
× contract_mismatch-4
× 120工具
× Dense Top-5
```

模型在该单元同时返回A004、E3C005、E3C027三个工具调用。单次结果无法判断这是稳定的契约边界错误，还是模型一次性波动。因此冻结完全相同的R2、R3，用三次配对结果测量波动性。

## 冻结范围

- R1基础单元：48；
- 新增重复：R2、R3；
- 每轮单元：48；
- 待授权请求：96；
- 三重复配对单元：48；
- 每个单元供应商尝试：1；
- 重试：禁止；
- 工具执行：禁止；
- 独立验证集访问：禁止；
- 确认性推断：禁止。

R2/R3不得改变：

- 两条任务文本；
- 三种0/4近邻条件；
- 17/120工具池及Schema顺序；
- Full Schema与三种Top-5候选视图；
- 系统提示词；
- 温度和模型；
- 离线评分规则；
- 48个基础单元的运行顺序。

R1结果只用于说明为什么需要重复，未用于调参或修改输入。

## 波动性分析契约

分析单位固定为：

```text
task_id × condition_id × tool_pool_size × method
```

每个单位取得R1、R2、R3三个`complete_call_correct`结果，并分类为：

| 分类 | 定义 |
| --- | --- |
| stable_correct | 3/3正确 |
| intermittent | 1/3或2/3正确 |
| stable_failure | 0/3正确 |

同时报告：

- 三次完全一致率；
- 每个配对单元的失败频率；
- 按近邻条件、方法、工具规模的描述性汇总；
- R1唯一失败是否在R2/R3复现；
- 单工具调用、工具选择、参数正确性和调用数量。

多数投票不会替代任务金标准，也不进行显著性检验。这一重复只回答开发问题：错误是否稳定、集中在哪个条件、是否值得扩展任务后进入正式先导。

## 本地门结果

所有13项检查通过：

- 输入和R1证据哈希有效；
- R2、R3均为48单元；
- 两轮均保持R1顺序；
- 48个三重复配对完整；
- 路由可见文件无金标字段；
- 请求尚未物化；
- 外部API调用0；
- 工具执行0；
- 独立验证集访问0。

6项重复开启包测试通过，manifest包含10项带SHA-256的冻结产物。

## 当前授权状态

```text
external_data_sharing_authorized = false
external_api_execution_authorized = false
provider_retry_authorized = false
tool_execution_allowed = false
request_payloads_materialized = false
```

因此，本文件和开启包的生成不构成API执行授权。

如需执行，建议使用以下精确授权范围：

> 同意将A004难例开启包中完全冻结的48个基础单元分别执行R2和R3，共96个请求，发送至DeepSeek并使用deepseek-v4-flash；任务、Schema、提示词、检索结果、评分规则和单元顺序均不得修改，每个单元只尝试一次，不重试、不执行任何冶金工具、不访问独立验证集，并保存逐条响应用于三重复离线波动分析。
