# CF-05 E3 A002/A003 治理采用与最小差异任务候选 v1

日期：2026-08-11

状态：家族治理已由项目负责人确认采用；最小差异开发任务候选已生成；`CF-05=in_progress`；`Core Frozen=false`

## 1. 治理采用记录

项目负责人已明确确认采用：

```text
2个可调用Schema端点
1个家族去重科学能力
主要工具、家族、Alternative Success、科学成功四层计分
A002/A003不进入H3对称近邻确认性金标
```

采用记录绑定：

- 治理候选文件SHA-256；
- 治理报告SHA-256；
- 产物清单SHA-256；
- 候选Git提交`0e2cb7c01bb8afc716a1d095cfd8bf7764782a13`；
- 确认时间和项目角色。

该记录是项目审批记录，不声称为密码学数字签名。它授权开发任务生成和后续正式集成准备，但没有自动修改研究协议、正式目录或正式金标。

## 2. 最小差异任务设计

选择8个处于A003 verified contract元素范围内的中性化学式：

```text
Fe2O3
H2SO4
CaCO3
CuSO4
(NH4)2SO4
Ca(OH)2
[Cu(NH3)4]SO4
FeS
```

每个化学式生成两条任务，共8组、16条：

```text
共同前缀：化学式 + 完全相同的冻结原子量

变体A：解析各元素化学计量数
变体B：计算摩尔质量并显式返回g/mol
```

每组任务在`任务：`之前的文本、公式、原子量和工具输入完全一致，只改变请求输出。8/8组通过最小差异检查。

## 3. 独立参考答案

参考答案的生成顺序固定为：

```text
人工给定化学式展开
→ 读取冻结合同原子量
→ 独立乘加计算摩尔质量
→ 冻结参考答案
→ 最后才调用A002/A003做后置一致性验证
```

因此，金标候选不是从被测工具输出反推得到。

| 化学式 | 独立展开 | 摩尔质量（g/mol） |
| --- | --- | ---: |
| Fe2O3 | Fe:2, O:3 | 159.6870 |
| H2SO4 | H:2, S:1, O:4 | 98.0720 |
| CaCO3 | Ca:1, C:1, O:3 | 100.0860 |
| CuSO4 | Cu:1, S:1, O:4 | 159.6020 |
| (NH4)2SO4 | N:2, H:8, S:1, O:4 | 132.1340 |
| Ca(OH)2 | Ca:1, O:2, H:2 | 74.0920 |
| [Cu(NH3)4]SO4 | Cu:1, N:4, H:12, S:1, O:4 | 227.7260 |
| FeS | Fe:1, S:1 | 87.9050 |

## 4. 非对称标签

### 元素计量任务

```text
A002：primary=1, family=1, scientific=1
A003：primary=0, family=1, scientific=0
```

### 摩尔质量任务

```text
A003：primary=1, family=1, scientific=1
A002：primary=0, family=1, alternative=1, scientific=1
```

这保证后续路由结果不会把“A002给出正确摩尔质量”误写为科学失败，也不会把“A003无法返回元素组成”误写为成功。

## 5. 后置验证结果

- 独立参考：8/8完成；
- A002元素计量与独立展开一致：8/8；
- A003摩尔质量和单位与独立参考一致：8/8；
- A002摩尔质量数值与独立参考一致但无显式单位：8/8；
- 本地确定性工具调用：16；
- 自动测试：17/17通过；
- 外部API调用：0。

## 6. 当前限制

任务候选只冻结了A002/A003核心工具对的关系，尚未逐一执行17或120工具池中的所有候选工具。因此每条任务均明确：

```text
full_catalog_acceptable_set_frozen = false
requires_pool_specific_acceptable_tool_revalidation = true
confirmatory_use_allowed = false
```

不能直接把该任务包送入确认性实验。

## 7. 证据

- 采用记录：`Tools/core_freeze/e3_routing/a002_a003_family_governance_adoption_v1.json`
- 构造配置：`Tools/core_freeze/e3_routing/a002_a003_minimal_pair_taskset_config_v1.json`
- 构造器：`Tools/core_freeze/e3_routing/build_a002_a003_minimal_pair_taskset.py`
- 测试：`Tools/core_freeze/tests/test_v11_cf05_e3_a002_a003_minimal_pair_taskset.py`
- 产物：`outputs/v11_cf05_e3_a002_a003_minimal_pair_taskset_v1_20260811/`

## 8. 下一步

下一步构建17/120工具下的哈希冻结候选视图，并对每条任务做池内可接受工具重算。完成后才能生成外部模型开发运行开启包；外部API调用仍需要单独授权。
