# E1c 后置评测开启包冻结记录

## 1. 冻结结论

E1c v1 已完成 24 道开发任务的六条件真实 API 运行，未发现需要修改实验逻辑、提示词、策略或评分规则的通用实现缺陷。根据协议，现已生成 36 道后置任务的本地开启包。

当前状态：

```text
evaluation_split_opened = true
external_api_execution_authorized = false
api_model_runs_performed = false
confirmatory_inference_allowed = false
core_frozen = false
```

这表示评测任务已经从完整任务集中提取并冻结，但尚未获得向外部模型发送数据的授权，也没有执行任何评测 API 请求。

## 2. 开启依据

| 字段 | 值 |
|---|---|
| 开启 ID | `E1C-EVALUATION-OPEN-V1-20260731` |
| 开发运行 ID | `E1C-RUN-71BA08D38E474CB4` |
| 开发证据提交 | `dd04b1cf904892452067b73c289dc5a5b6bad8d1` |
| 开发条件单元 | 144 |
| 开发运行状态 | completed |
| 开发请求失败/重试 | 0/0 |
| 开启包任务数 | 36 |
| 计划条件单元 | 216 |
| 用户授权范围 | 生成本地开启包 |

开发结果已经证明：

- 六条件真实 API 链路可执行；
- 动作、参数、函数调用和最终答案均可解析；
- 五个验证工具可以执行；
- 错误阶段归因有效；
- 运行产物 manifest 完整；
- 开发结果中的全不调用、全调用和参数非完全匹配均属于模型行为，而不是运行器故障。

因此，不再依据开发结果修改 E1b 策略 v1、E1c 提示词 v1 或评分规则。

## 3. 后置任务构成

| 工具 | 任务数 |
|---|---:|
| A001 | 6 |
| A002 | 6 |
| A003 | 12 |
| A004 | 8 |
| B019 | 4 |
| 合计 | 36 |

冻结动作分布：

- `CALL_VERIFIED_TOOL`：10；
- `ANSWER_WITHOUT_TOOL`：26。

六条件、单次冻结重复共计划运行：

```text
36 × 6 × 1 = 216 个条件单元
```

## 4. 关键哈希

| 产物 | SHA-256 |
|---|---|
| 源完整任务集 | `4e079bab547df3e762b06a765f386e47f7fbdf370093bcc587b9395c968a97cc` |
| 后置任务快照 | `0449dcd13340dfd8c39256263f2b56a6f4af7c2297a654c5c6e0f8a57444ee41` |
| 研究协议 | `6695f491aefc0f44ee42c95ba15ff0dba6c1f9468f6a71503d2915426db3f42d` |
| 冻结提示词 | `7868874805e6f119d9f53875b9b713fd1af432d29bec2293fbd2b4a810f322d9` |
| E1b 冻结策略 | `4d34ddc0a8d53d46f0aabf1469469dab243b9ddb6c03a5e8e849b9763801c1d5` |
| 评测运行配置 | `71127dbdd9764eddf4e3d9666bb374aa84d59705688f1caae6bd8e944cc93540` |
| 评测模式运行器 | `4d36d239b42b7feef89fb823b32befc00d998ff29291515afd791a40be8df435` |
| 评分器 | `c33e48c188c31a743e234a3b6e6cdbaed221d582e8d5b74ee430959033685190` |
| 开启记录 | `d3a6e97536027983cbd92497977e2b2f25fb1133b9dd4ab3921c1038521352bd` |
| 执行授权请求 | `48ed6fb2f58ad6d779654ae39b3ad43fcb16be708d3ea13c90ceac7db1325849` |
| 开启包 manifest | `4a3b05aa4b28ef0d8e4660519ce7af9aba800fc3eac8331142259ed45b771779` |

## 5. 运行器审计强化

开发运行器原先只允许 `runner_development`，并把报告状态固定为评测未开启。为支持后置评测，新增了受控评测模式，但没有改变：

- 六个实验条件；
- 条件顺序；
- 提示词内容；
- 边界策略；
- 工具 Schema；
- 工具执行逻辑；
- 参数完全匹配规则；
- 最终答案评分规则；
- 首要失败阶段优先级。

评测模式新增的只是执行门槛和状态记录：

1. 必须提供独立执行授权文件；
2. 授权决策必须为 `authorized_to_execute_evaluation`；
3. 授权必须绑定题目、提示词、配置和运行器 SHA-256；
4. 授权必须绑定数据集、模型、端点和 36 题数量；
5. 正式评测禁止任务抽样、条件抽样和重复次数覆盖；
6. 评测输出必须快照执行授权并正确记录 `evaluation_split_opened=true`。

开发模式继续拒绝评测授权文件，并继续要求 `evaluation_split_opened=false`。

## 6. 外部执行仍需单独授权

开启包中的 `execution_authorization_request.json` 已精确列出拟发送到 DeepSeek 的载荷：

- 36 道后置任务文本；
- E1c 冻结提示词；
- 5 个验证工具 Schema；
- 调用过程中产生的工具计算结果。

目标为：

```text
endpoint = https://api.deepseek.com
model = deepseek-v4-flash
scheduled_cells = 216
```

只有用户针对该精确请求再次明确授权后，才能生成 `execution_authorization.json` 并运行 API。开启包生成授权不能替代外部执行授权。

## 7. 解释边界

E1c 后置评测仍是五工具可执行真值条件下的机制实验。即使运行完成，也不表示：

- 120 工具规模路由已经通过；
- Track A/B 金标准已经完成；
- CF-01 至 CF-11 已全部通过；
- `Core Frozen=true`；
- 结果可直接外推到神经网络预测工具或开放式冶金工程决策。

后置结果只能检验冻结 E1c v1 条件下的边界、工具选择、参数、执行和结果表达损失。
