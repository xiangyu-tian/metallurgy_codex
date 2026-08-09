# A003 120工具版 Lexical Top-5 候选实现 v1

日期：2026-08-09

状态：`candidate_implementation_passed_local_gate`

外部API调用：`0`

## 实现

新实现使用无外部依赖、可哈希复现的加权Unicode n-gram BM25：

- 文本统一进行NFKC与大小写归一化；
- 中文使用2/3字n-gram，英文和Schema字段名使用字母数字Token；
- 数值Token不进入索引，避免任务答案和原子量主导召回；
- 索引覆盖冻结Schema注册表全部137项；
- 检索时只允许在当前17或120工具池内排序；
- 并列时按`tool_id`升序，Top-K固定为5；
- 查询只读取`problem_text`，不读取目标工具、可接受工具或评分规则。

字段权重在运行前固定，优先强调工具名称、核心方法、输入和输出，同时保留场景、边界、函数描述和参数描述信息。完整配置和索引文档哈希均进入证据包。

## 本地干跑

对A003开启包中的24个`lexical_top5`单元生成了候选视图：

```text
2个严格/宽松任务
× 2个规模（17、120）
× 3个条件（none-0、lexical-8、functional_overlap-8）
× 2个池重复（A、B）
= 24
```

本地门检查包括：

- 每个单元恰好5个候选；
- 候选全部来自当前工具池；
- 同一输入重复检索的工具顺序和分数完全一致；
- 候选视图不存在金标字段；
- 开发集Acceptable Recall@5和目标A003 Recall@5达到预设门槛；
- 不调用DeepSeek，不执行任何冶金工具。

这些指标只用于证明实现具备进入后续开发运行的资格，不是H3/H4结果，也不能外推到其他工具家族。

## 当前方法状态

| 方法 | 当前状态 |
| --- | --- |
| Full Schema | ready |
| Lexical Top-5 | candidate implementation passed local gate |
| Dense Top-5 | pending implementation |
| Hierarchical Top-5 | pending implementation |

由于四种方法尚未全部就绪，A003外部执行授权门继续关闭。下一步应构建Dense Top-5的冻结模型/向量快照，或先完成不依赖新模型下载的Hierarchical Top-5。
