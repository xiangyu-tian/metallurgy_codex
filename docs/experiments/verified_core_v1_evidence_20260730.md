# verified_core v1 验证证据

## 结论

首批五个确定性工具已经在**明确、受限的合同范围内**通过独立参考验证：

```text
A001 单位换算
A002 化学式解析
A003 摩尔质量计算
A004 成分归一化
B019 二元两相杠杆规则
```

验证结果：

```yaml
validation_id: VERIFIED-CORE-V1-20260730
contract_count: 5
reference_case_count: 27
passed_case_count: 27
failed_case_count: 0
validation_status: passed
core_frozen: false
```

机器可读报告位于：

```text
outputs/verified_core_v1_20260730/validation_report.json
outputs/verified_core_v1_20260730/artifact_manifest.json
```

## 为什么可以不依赖专家逐题标注

本批任务的真值不是由AI或非专业人员判断，而是来自：

1. 版本化工具合同；
2. SI定义、IUPAC/CIAAW原子量等外部来源；
3. 独立冻结的输入—输出参考案例；
4. 量纲、守恒、比例不变性等可执行约束；
5. 对非法输入和适用边界的程序化判定。

因此，人工的作用是审查合同、来源和实验治理，不是逐题凭经验填写“正确答案”。

## 本轮发现并修复的问题

### A001

- 原包装层使用宽松量纲模式，可能允许`kg → m`；
- 底层失败没有被包装层传播；
- 仿射温标只返回乘法因子，缺少偏移量。

修订后采用严格量纲检查，并将变换统一表示为：

```text
target = source × conversion_factor + conversion_offset
```

### A002 / A003

原解析器可能只解析合法前缀并忽略非法后缀，例如`Fe2O3abc`。
现改为完整词法消费的递归下降解析器，拒绝：

- 未消费字符；
- 未知元素；
- 空括号和不匹配括号；
- 前置系数；
- 零或非法计量数。

支持范围明确限制为普通中性化学式，不包含水合物点号、离子电荷、同位素和反应系数。

### A004

增加了对对象类型、数值类型、布尔值、NaN、Infinity、负值、全零向量、
非有限总和及非法容差的拒绝。验证同时覆盖正比例缩放不改变归一化结果。

### B019

历史用例表明该工具同时接收0—1小数和0—100百分数。杠杆规则对共同线性标度
不变，因此没有强行删除百分数支持，而是增加：

```text
composition_basis = fraction | percent | auto
```

确认性任务必须显式使用`fraction`或`percent`；`auto`只用于旧调用兼容。

## 独立性说明

`reference_cases_v1.json`中的期望值是冻结数据，不由生产工具生成。
验证程序分别：

```text
读取冻结期望
→ 调用生产工具
→ 比较结构、数值、容差和错误代码
→ 检查每个工具的正常/边界覆盖
→ 验证合同哈希与运行时版本
```

这避免了“用工具自己的输出来证明工具正确”的循环验证。

## 外部依据

- BIPM, *The International System of Units (SI Brochure), 9th edition*：
  <https://www.bipm.org/en/publications/si-brochure>
- NIST SP 811, *Guide for the Use of the International System of Units*：
  <https://www.nist.gov/pml/special-publication-811>
- IUPAC, *Periodic Table of Elements*：
  <https://iupac.org/what-we-do/periodic-table-of-elements/>
- CIAAW, *Standard Atomic Weights*：
  <https://ciaaw.org/atomic-weights.htm>
- IUPAC Gold Book, *amount fraction*：
  <https://goldbook.iupac.org/terms/view/A00296>

## 可以支持的下一步

这五个工具现在可以用于：

1. E1b的`No Tool`与`Forced Verified Tool`成对任务生成；
2. E2的缺参、单位缺失、量纲不符、越界和不可执行变换；
3. E3的小规模工具选择、参数生成、执行正确性和证据链评分。

但以下结论仍然禁止：

- “17个工具都已验证”；
- “120个工具都能可靠计算”；
- “自然冶金问题已有专家金标准”；
- “Core Frozen已经完成”。

首批E1b受控任务已经生成：

```text
outputs/e1b_pilot_v1_20260730/e1b_tasks.json
```

共14个任务、28个成对条件运行单元。当前状态仅为`prepared`，下一阶段是实现统一
JSON回答提取与评分，然后在冻结的开发性模型配置下进行少量重复运行。
