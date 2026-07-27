# CF-11最小实现测试证据

## 记录状态

- 日期：2026-07-27
- 统计接口：`1.0-rc1.1`
- 协议：`1.0-rc3.1`
- 数据规范：`1.0-rc3`
- 结论：最小数据契约和配对分析测试通过；CF-11继续保持`in_progress`

---

## 1. 本轮验证范围

已验证：

- 输入Schema与跨字段状态校验；
- 请求状态和执行状态分离；
- H3正、负、零差值；
- H3只读取120工具`controlled_dose`的8近邻条件；
- H4只读取`mixed_realistic`的17与120工具；
- H4固定三项层次化路由对比及Holm校正；
- 缺失配对被审计且不插补；
- A—E工具池先聚合、模型重复后汇总；
- 行顺序打乱不改变点估计和Bootstrap；
- 最小报告明确保留`formal_mixed_effect_model=not_run`和`cf11_status=in_progress`。

未验证：

- 正式H3/H4广义线性混合效应模型；
- 模型不收敛时的预注册简化链；
- 正式CSV输出全集；
- 真实候选数据；
- 统计审查人和项目负责人的审批。

---

## 2. CF-11合成测试

执行命令：

```powershell
& '.\.venv\Scripts\python.exe' -m compileall -q 'Tools\core_freeze'
& '.\.venv\Scripts\python.exe' -m unittest discover -s 'Tools\core_freeze\tests' -t . -v
```

结果：

```text
Ran 13 tests
OK
```

覆盖文件：

- `test_pairing.py`
- `test_aggregation.py`
- `test_missingness.py`
- `test_condition_filters.py`

---

## 3. 既有离线回归

仓库正式离线回归入口：

```powershell
& '.\.venv\Scripts\python.exe' 'Tools\run_baseline_tests.py'
```

结果：

```text
Ran 44 tests
OK
Golden benchmark: 138 cases, 17 models, baseline 2.0.0
```

全目录`unittest discover`另外发现：

- 44项通过；
- 1项PostgreSQL集成测试按环境开关跳过；
- `test_a001.py`因当前虚拟环境未安装其既有`pytest`依赖而无法导入。

该依赖缺失发生在本轮变更之外；本轮没有为执行可选旧测试而新增依赖。

---

## 4. 冻结判断

本证据只能证明最小实现的数据流和主要防错规则能够运行，不能证明正式统计推断已经实现或通过审查。

因此：

```text
CF-11 = in_progress
Core Frozen = false
```
