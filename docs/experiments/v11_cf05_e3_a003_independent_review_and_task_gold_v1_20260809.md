# v1.1 CF-05 A003 独立池审计与任务金标准重算

## 1. 结论

A003 的受控近邻池已完成独立于构造器的复核，结构和关系证据均通过；复核同时发现旧任务的 `acceptable_tools` 在候选近邻产生后已经过期，因此先阻止模型运行，再按冻结容差完成逐任务重算。

当前状态：

```yaml
pool_structure_review: passed
relation_separation_review: passed
runtime_evidence_review: passed
task_level_primary_acceptable_sets: revalidated
development_routing_run_allowed: true
confirmatory_use_allowed: false
CF-05: in_progress
Core Frozen: false
```

## 2. 独立池审计

审计程序不导入 A003 池构造器，而是从哈希冻结的产物重新计算：

- 17、50、100、120 四个规模；
- A—E 五个工具池重复；
- `none-0`、`lexical-4/8`、`contract_mismatch-4/8` 五个条件；
- 共 100 个池记录；
- 目标工具唯一性、精确近邻剂量、配对中性基底、近邻插槽和跨规模嵌套关系；
- 8 个词法近邻与 8 个契约错配近邻互斥；
- 候选工具正常与失败契约用例完整。

两类关系的机器判据为：

```text
lexical:
  algorithmic_lexical_candidate = true
  same_core_method = false

contract_mismatch:
  same_scenario = true
  same_core_method = true
  algorithmic_lexical_candidate = false
  provable_contract_mismatch_neighbor = true
  relation_evidence_passed = true
```

该定义对应 v1.1 协议中的“适用域契约不匹配近邻”，不声称获得了专家确认的抽象功能相似金标准。

## 3. 为什么不能直接复用旧 `acceptable_tools`

绑定的 12 条 A003 任务最初都只有：

```json
{"acceptable_tools": ["A003"]}
```

但候选工具 E3C004 具有相同的直接输入和输出契约：

```text
formula → molar_mass (g/mol)
```

因此，不能仅因它被放入近邻池就预先把它判为错误工具。必须用每条任务已经冻结的数值容差重新计算其是否可接受。

## 4. 任务级重算结果

主要选择估计对象固定为：

> 单工具直接满足任务输入、目标量、单位和预冻结数值容差。

结果如下：

| 任务类型 | 任务数 | 主要可接受工具集合 |
|---|---:|---|
| 严格容差 `±0.0001 g/mol` | 6 | `A003` |
| 宽松容差 `±0.1 g/mol` | 6 | `A003, E3C004` |

E3C004 在六条严格任务上均超过容差，在六条宽松任务上均落入容差。因此任务级可接受集合不是工具级常量，而取决于任务的冻结精度要求。

需要额外换算或解释其他输出的候选工具不静默进入主要 `acceptable_tools`，但后续必须单独报告 `Alternative Success`，避免把可推导成功与直接契约满足混为一谈。

## 5. 证据

```yaml
independent_review_manifest_sha256: 7a7b56f309728d5811b76c68e17f36b7819adae6577a9954edb0879e6131ae60
task_gold_revalidation_manifest_sha256: fa60ab298d43506e933e41de97a9f03befa9a897c4cb5a3f1f3506df85c0bdd0
acceptable_tools_registry_sha256: bf481d4f98ca8627af4059509b5f54d54f6b9aab9c9e70d45bc1fd86cc5b49ec
direct_candidate_execution_sha256: 1b66a25cf15348d241552dd0b20047746d64dbb176e1bcbeb2a5b7e68fc403fa
external_api_calls: 0
```

产物目录：

```text
outputs/v11_cf05_e3_a003_independent_review_v1_20260809/
outputs/v11_cf05_e3_a003_task_gold_revalidation_v1_20260809/
```

## 6. 下一步

A003 现在具备开发性路由先导的前置条件。下一步应构建哈希绑定的 A003 路由开启包，固定：

- 12 条任务及任务级可接受工具集合；
- 五个近邻剂量条件；
- 17/50/100/120 工具规模；
- A—E 工具池重复；
- 开发期方法和模型重复；
- 只记录工具选择与参数，不执行候选工具；
- 不允许确认性推断。

CF-05 仍保持 `in_progress`，因为当前只有 A003 一个目标达到 8/8，尚不足以支撑跨目标工具家族的正式 H3/H4 估计。
