# A003 四方法路由开发执行开启包 v1

日期：2026-08-09

状态：`prepared_eligible_pending_explicit_authorization`

外部API调用：`0`

## 作用

该开启包把此前分别实现的四种路由方法合并到同一个96单元A003开发网格：

```text
2个任务
× 12个工具池（17/120、A/B、none/lexical/functional_overlap）
× 4种方法
= 96个单次开发单元
```

四种方法各占24单元：

- Full Schema直接使用当前池中的全部17或120个函数Schema；
- Lexical Top-5读取哈希绑定的24个词法候选视图；
- Dense Top-5读取哈希绑定的24个本地向量候选视图；
- Hierarchical读取哈希绑定的24个层次化候选视图。

## 请求冻结方式

为避免在96个单元中重复存储大体积Schema，开启包采用内容寻址结构：

- `a003_routing_schema_views.json`保存45个去重后的完整Schema视图；
- `a003_routing_request_blueprints.json`保存96个单元及其Schema视图引用；
- 每个单元记录可重建的API请求体SHA-256；
- 测试逐单元重建完整请求体并复算哈希；
- `thinking=disabled`作为适配器设置单独冻结，不混入API请求体哈希。

96个单元仍使用完全相同的第二阶段系统提示、模型、温度、最大输出长度和`tool_choice=auto`。方法间唯一允许变化的是可见Schema集合。

## 预检结果

- 四方法均已通过本地候选门；
- 恰好96个请求蓝图，每种方法24个；
- Full Schema视图仅为17或120个工具；
- 三种检索方法均恰好暴露5个工具；
- 所有候选均位于对应的冻结工具池内；
- 路由材料中不存在金标字段或API密钥；
- 未访问40条独立验证集；
- 未调用外部API，未执行冶金工具；
- CF-05仍为`in_progress`，Core Frozen仍为`false`。

## 下一道门

技术上，该包已经具备执行一次DeepSeek开发性选择器运行的条件；治理上仍未获授权。`execution_authorization_request.json`保持：

```text
eligible = true
external_data_sharing_authorized = false
external_api_execution_authorized = false
tool_execution_allowed = false
```

后续只有在用户明确同意发送两个A003开发任务文本和这些冻结Schema视图后，才能创建独立授权记录与执行器。该运行仍是开发性先导，不能用于H3/H4确认性推断。
