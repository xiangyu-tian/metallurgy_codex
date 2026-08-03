# v1.1 CF-05 E3 第二批候选运行与证据准入

## 结论

第二批12个草案候选已经完成离线可执行性审查，其中10个形成了真实可调用包装器；9个进入非正式关系证据注册表，1个因真实名称未达到冻结Dice阈值而保留为“关系证据不足”；另有2个 pycalphad 工作流因缺少冻结TDB而保留编号、暂停实现与准入。

```yaml
registration_package_id: V11-CF05-E3-REGISTRATION-CANDIDATES-BATCH2-V1-20260803
admission_decision_id: V11-CF05-E3-CANDIDATE-ADMISSION-BATCH2-V1-20260803
candidate_id_reservation_count: 12
implemented_candidate_count: 10
blocked_candidate_count: 2
runtime_case_count: 30
runtime_pass_count: 30
lexical_relation_admission_count: 5
contract_mismatch_relation_admission_count: 4
relation_evidence_held_count: 1
combined_relation_registry_count: 13
formal_catalog_size: 120
formal_pool_inclusion_count: 0
external_api_calls: 0
core_frozen: false
```

## 可执行候选及关系

每个候选都有一个正常、一个边界和一个失败用例。关系类型必须通过冻结的Dice/结构化契约算法，并且每个候选只占一个关系槽位。

| 候选 | 目标 | 能力 | 准入关系 |
|---|---|---|---|
| `E3C006` | A001 | Pint显式上下文维度变换 | 契约错配 |
| `E3C007` | A002 | RDKit SMILES结构解析 | 证据不足，不准入 |
| `E3C008` | A002 | RDKit SMARTS查询解析 | 词法近邻 |
| `E3C009` | A002 | RDKit规范SMILES | 词法近邻 |
| `E3C010` | A003 | RDKit精确同位素分子量 | 词法近邻 |
| `E3C011` | A003 | RDKit重原子分子量 | 契约错配 |
| `E3C012` | A004 | pymatgen最简组成比 | 词法近邻 |
| `E3C013` | A004 | pymatgen单元素原子分数 | 词法近邻 |
| `E3C014` | A004 | pymatgen单元素质量分数 | 契约错配 |
| `E3C015` | A004 | pymatgen质量到摩尔组成转换 | 契约错配 |

`E3C007`的正常、边界和失败运行契约均通过，但其真实名称Dice为0.10、完整契约文本Dice为0.084507，低于冻结阈值0.20/0.12。运行成功不能替代关系证据，因此没有通过改名或拼接目标名称来制造词法相似度。

其余9项关系是实验工具池的候选证据，不代表新增9个独立科学功能，也不授权把它们放入正式确认性工具池。

## pycalphad阻断决定

`E3C016`和`E3C017`没有被伪装成“可运行”候选：

| 候选 | 草案能力 | 阻断原因 |
|---|---|---|
| `E3C016` | 相稳定性筛查 | 没有可再分发、按哈希冻结且带独立期望结果的TDB |
| `E3C017` | 二元相图映射 | 除TDB外，节点步进、收敛条件和期望相区也未冻结 |

pycalphad包已经安装并不等于科学工具可复现。解除阻断至少需要冻结：数据库文件、许可证、SHA-256、组元、相、条件、求解/映射设置以及独立参考结果。

## 缺口复算

第二批准入建立在第一批结果之上：

| 目标 | 词法近邻 | 契约错配近邻 |
|---|---:|---:|
| A001 | 0 | 1 |
| A002 | 3 | 1 |
| A003 | 6 | 2 |
| A004 | 3 | 3 |
| B019 | 4 | 0 |

总缺口变化为：

```text
lexical_gap: 29 -> 24
contract_mismatch_gap: 37 -> 33
```

目前仍没有任何目标同时达到8个词法近邻和8个契约错配近邻，所以不能开始正式8近邻确认性池。A003距离词法8最近，但契约错配仍缺6项；B019仍受TDB资产阻断。

## 产物

```text
outputs/v11_cf05_e3_registration_candidates_batch2_v1_20260803/
outputs/v11_cf05_e3_candidate_admission_batch2_v1_20260803/
```

Manifest SHA-256：

```text
registration: 9e0f13d1d84c2b4a57015975e3184cf8bac07b9fb5dfd741c8924fe108a71039
admission:    95dd858ded897ede49eccb354538d924e08e361151aad73bee6360c733ab13b5
```

## 下一执行点

下一批不再平均铺开候选，而是优先补齐一个可形成0/4/8剂量的目标。依据当前缺口，优先顺序为：

1. A003：新增2个合格词法近邻和6个契约错配近邻；
2. A004：新增5个词法近邻和5个契约错配近邻；
3. B019：先解决TDB许可与冻结，再开发相平衡近邻；
4. 达到单目标8/8后，才构造该目标的0/4/8嵌套开发池并做泄漏审计。
