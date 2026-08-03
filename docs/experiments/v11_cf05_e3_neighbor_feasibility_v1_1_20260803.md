# v1.1 CF-05 E3近邻可行性审计v1.1

## 1. 修正结论

v1使用字符二元组Dice时，没有先从文本中删除“计算、预测、校验”等通用功能词，导致共享通用后缀的工具被计为词法候选。v1.1在生成二元组前删除冻结的通用词表，并新增防回归测试。

```yaml
audit_id: V11-CF05-E3-NEIGHBOR-FEASIBILITY-V1.1-20260803
supersedes_audit_id: V11-CF05-E3-NEIGHBOR-FEASIBILITY-V1-20260803
status: blocked_evidence_generated
catalog_size: 120
h3_paired_8_eligible_target_count: 0
formal_controlled_dose_pools_generated: false
external_api_calls: 0
```

旧v1目录及Manifest保持原始字节，不被静默覆盖。

## 2. 修正后的目标级结果

| 目标 | 词法候选 | 可证明契约错配近邻 | 词法缺口 | 契约错配缺口 |
|---|---:|---:|---:|---:|
| A001 单位换算 | 0 | 0 | 8 | 8 |
| A002 化学式解析 | 1 | 0 | 7 | 8 |
| A003 摩尔质量计算 | 4 | 0 | 4 | 8 |
| A004 成分归一化 | 1 | 0 | 7 | 8 |
| B019 杠杆规则计算 | 4 | 0 | 4 | 8 |
| 合计缺口 | — | — | 30 | 40 |

共享真实领域词仍可构成词法候选。例如“摩尔质量”和“铸坯质量”共享“质量”，即使科学功能不同，也符合纯词法干扰的定义。仅共享“计算”等通用词则不再计入。

## 3. 容量结论

容量结论与v1一致：

```text
120规模单类型0/4/8池：至少128条目录
120规模双类型0/4/8池：至少136条目录
```

但是136只是工具数量容量下限。当前目标级关系缺口为70槽；若每个槽都由不同工具满足，保守目录规模为190条。候选工具只有在分别证明其与目标的关系后，才能跨目标复用。

## 4. 产物

```text
outputs/v11_cf05_e3_neighbor_feasibility_v1_1_20260803/
```

Manifest SHA-256：

```text
b1a2669dee94bb2a2665fb8ba08226daf00e766165df761dd7bae0e475f744e8
```
