# CF-05 E3：B019 参数证据忠实性审计 v1

## 结论

对多目标现实混合工具池 R2 中 16 个 B019 调用重新审计后发现：工具选择和杠杆规则所需的数值参数均正确，但 11 个调用加入了请求中不存在的 `component="B"`。

| 指标 | 原评分 | 严格证据口径 |
| --- | ---: | ---: |
| B019 单元 | 16 | 16 |
| 工具选择正确 | 16/16 | 16/16 |
| 参数正确/忠实 | 16/16 | 5/16 |
| 无依据的可选参数 | 未惩罚 | 11/16 |

严格参数证据忠实率为 31.25%。这不表示 11 个相分数计算结果错误，而是说明现有参数评分没有惩罚模型自行补充的无依据字段，高估了调用证据的忠实性。

## 问题来源

B019 verified contract 将以下四项列为必需输入：

```text
overall_composition
phase1_composition
phase2_composition
composition_basis
```

但当前运行 Schema 存在两处不一致：

1. `composition_basis` 没有进入 `required`，并允许默认值 `auto`；
2. 可选字段 `component` 默认值为 `"B"`。

确认性任务明明要求显式声明 `fraction` 或 `percent`，Schema 却允许省略；题目没有说明具体组元，Schema 的默认值又诱导模型补出 `"B"`。

11 个无依据字段的分布为：

| 方法 | 数量 |
| --- | ---: |
| Full Schema | 2 |
| Lexical Top-5 | 4 |
| Dense Top-5 | 1 |
| Hierarchical | 4 |

| 工具规模 | 数量 |
| --- | ---: |
| 17 | 5 |
| 120 | 6 |

因此该问题不是某一种路由方法或某一个工具规模独有，而是共享 Schema 契约导致的系统性参数偏差。

## 正式 Schema 候选

本轮生成了一个不修改正式目录的 B019 Schema 候选：

- 将 `composition_basis` 设为必填；
- 只允许 `fraction` 和 `percent`，排除 `auto`；
- 删除 `composition_basis` 默认值；
- 删除 `component="B"` 默认值；
- 仅当请求显式给出组元名称时才允许 `component`；
- 设置 `additionalProperties=false`。

候选文件位于：

```text
outputs/v11_cf05_e3_b019_parameter_fidelity_audit_v1_20260811/
  b019_formal_schema_candidate.json
```

## 研究意义

这一结果补充了项目的第三类可靠性问题：

```text
选对工具
≠ 参数完全可信
≠ 输入证据可追溯
```

模型即使选中了正确工具，也可能通过 Schema 默认值或无依据补全生成“表面合法、来源不明”的参数。因此正式指标需要区分：

1. 工具选择正确；
2. 必需参数数值正确；
3. 参数是否全部有请求或上游证据支撑；
4. 计算输出是否满足物理规律。

## 状态与边界

- 本轮未调用外部 API；
- 未执行 B019；
- 未声称既有相分数结果错误；
- 未修改正式 Schema 目录或 verified contract；
- `CF-05=in_progress`；
- `core_frozen=false`。

下一步应实现 B019 严格参数门候选，在调用前阻止 `auto`、缺少显式标度及无依据 `component`，并在既有 16 个响应上离线回放。只有通过回放和边界挑战后，才考虑更新正式 API Schema。
