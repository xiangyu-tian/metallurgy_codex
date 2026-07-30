"""
A 系列模型：通用数据与校验
A001 单位换算 → 委托到 a001_unit_conversion
A002 化学式解析
A003 摩尔质量计算
A004 成分归一化
A005 元素质量守恒校验
"""
from __future__ import annotations
import math
import re
from typing import Dict, List, Optional, Tuple

from .base import (
    BaseModelTool, ModelResult, InputField, OutputField,
    BoundaryCheck, BoundaryWarning, InvocationContext, Provenance,
)
from .chemical_data import ELEMENT_ATOMIC_WEIGHTS


# ── A001 单位换算 ──

class A001_UnitConversion(BaseModelTool):
    model_id = "A001"
    name = "单位换算"
    scenario = "通用数据与校验"
    priority = "P0"
    version = "1.0.0"
    applicable_boundary = "支持线性换算和温度偏移换算；超界返回警告"

    input_fields = [
        InputField("value", "数值", type="number", required=True, description="待换算的数值"),
        InputField("source_unit", "源单位", type="string", required=True, placeholder="如 °C, kg, MPa"),
        InputField("target_unit", "目标单位", type="string", required=True, placeholder="如 K, g, psi"),
    ]

    output_fields = [
        OutputField("value", "换算值", type="number"),
        OutputField("source_unit", "源单位", type="string"),
        OutputField("target_unit", "目标单位", type="string"),
        OutputField("conversion_factor", "换算因子", type="number"),
        OutputField("conversion_offset", "换算偏移量", type="number"),
        OutputField("category", "单位类别", type="string"),
    ]

    def invoke(self, params: dict, context: Optional[InvocationContext] = None) -> ModelResult:
        # 尝试委托到 a001_unit_conversion（如果已安装）
        try:
            from a001_unit_conversion import convert_units
            r = convert_units(
                params["value"], params["source_unit"],
                params["target_unit"], strict=True
            )
            if not r.success:
                error = r.error or "单位换算失败"
                error_code = (
                    "UNIT_MISMATCH"
                    if "量纲不匹配" in error
                    else "INVALID_INPUT"
                )
                return ModelResult(
                    success=False,
                    error=error,
                    error_code=error_code,
                )

            warnings = []
            if hasattr(r, 'warnings') and r.warnings:
                for w in r.warnings:
                    warnings.append(BoundaryWarning(
                        field=getattr(w, 'field', 'value'),
                        message=getattr(w, 'message', str(w)),
                        level=getattr(w, 'level', 'warning'),
                    ))

            return ModelResult(
                success=True,
                result={
                    "value": r.value,
                    "source_unit": r.source_unit,
                    "target_unit": r.target_unit,
                    "conversion_factor": getattr(r, 'conversion_factor', r.value / params['value'] if params['value'] else 0),
                    "conversion_offset": getattr(r, 'conversion_offset', 0.0),
                    "category": getattr(r, 'category', ''),
                },
                boundary_check=BoundaryCheck(
                    passed=len([w for w in warnings if w.level == 'error']) == 0,
                    warnings=warnings,
                ),
            )
        except ImportError:
            pass

        # 内置简易换算（作为 fallback）
        value = float(params["value"])
        src = params["source_unit"]
        tgt = params["target_unit"]

        # 温度专用
        temp_conversions = {
            ("°C", "K"): (lambda v: v + 273.15, 1),
            ("K", "°C"): (lambda v: v - 273.15, 1),
            ("°C", "°F"): (lambda v: v * 9/5 + 32, 9/5),
            ("°F", "°C"): (lambda v: (v - 32) * 5/9, 5/9),
        }
        if (src, tgt) in temp_conversions:
            fn, factor = temp_conversions[(src, tgt)]
            result = fn(value)
            return ModelResult(
                success=True,
                result={
                    "value": round(result, 6),
                    "source_unit": src,
                    "target_unit": tgt,
                    "conversion_factor": factor,
                    "conversion_offset": fn(0.0),
                    "category": "温度",
                },
            )

        # 常用单位映射到 SI base
        unit_to_si = {
            "kg": ("质量", 1), "g": ("质量", 0.001), "t": ("质量", 1000), "lb": ("质量", 0.453592),
            "m": ("长度", 1), "cm": ("长度", 0.01), "mm": ("长度", 0.001), "km": ("长度", 1000),
            "Pa": ("压强", 1), "kPa": ("压强", 1000), "MPa": ("压强", 1e6),
            "atm": ("压强", 101325), "bar": ("压强", 1e5), "psi": ("压强", 6894.76),
            "J": ("能量", 1), "kJ": ("能量", 1000), "cal": ("能量", 4.184),
            "W": ("功率", 1), "kW": ("功率", 1000), "MW": ("功率", 1e6),
            "s": ("时间", 1), "min": ("时间", 60), "h": ("时间", 3600),
        }

        if src in unit_to_si and tgt in unit_to_si:
            cat_src, factor_src = unit_to_si[src]
            cat_tgt, factor_tgt = unit_to_si[tgt]
            if cat_src != cat_tgt:
                return ModelResult(
                    success=False, error=f"量纲不匹配: {cat_src} vs {cat_tgt}",
                    error_code="DIMENSION_MISMATCH",
                )
            si_value = value * factor_src
            result = si_value / factor_tgt
            return ModelResult(
                success=True,
                result={
                    "value": round(result, 10),
                    "source_unit": src,
                    "target_unit": tgt,
                    "conversion_factor": round(factor_src / factor_tgt, 10),
                    "conversion_offset": 0.0,
                    "category": cat_src,
                },
            )

        return ModelResult(
            success=False, error=f"不支持的换算: {src} → {tgt}",
            error_code="UNSUPPORTED_CONVERSION",
        )


# ── 化学式解析辅助 ──

# 元素符号、正计量数和括号。解析必须完整消费输入。
_FORMULA_TOKEN_RE = re.compile(r'[A-Z][a-z]?|\d+(?:\.\d+)?|[()\[\]{}]')
_BRACKET_CLOSE = {'(': ')', '[': ']', '{': '}'}
_BRACKET_OPEN = {value: key for key, value in _BRACKET_CLOSE.items()}

def parse_formula(formula: str) -> Tuple[Optional[Dict[str, float]], Optional[str]]:
    """
    解析化学式，返回 {元素: 数量} 和错误信息。
    支持括号嵌套：Fe2(SO4)3, Mg(OH)2, [Cu(NH3)4]SO4
    """
    formula = formula.strip()
    if not formula:
        return None, "化学式为空"

    try:
        tokens = _tokenize_formula(formula)
        counts, next_index = _parse_formula_group(tokens, 0, None)
        if next_index != len(tokens):
            return None, f"化学式包含未解析内容: {tokens[next_index]}"
    except ValueError as e:
        return None, str(e)

    # 验证元素存在
    for elem in counts:
        if elem not in ELEMENT_ATOMIC_WEIGHTS:
            return None, f"未知元素: {elem}"

    return counts, None


def _tokenize_formula(formula: str) -> List[str]:
    """完整词法分析；任何未消费字符都视为非法输入。"""
    tokens = []
    position = 0
    while position < len(formula):
        match = _FORMULA_TOKEN_RE.match(formula, position)
        if match is None:
            raise ValueError(
                f"化学式含非法字符或语法，位置 {position}: {formula[position]!r}"
            )
        tokens.append(match.group(0))
        position = match.end()
    return tokens


def _positive_multiplier(token: str) -> float:
    multiplier = float(token)
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise ValueError(f"化学计量数必须为正数: {token}")
    return multiplier


def _parse_formula_group(
    tokens: List[str],
    index: int,
    expected_close: Optional[str],
) -> Tuple[Dict[str, float], int]:
    """递归下降解析化学式分组，并保留全部元素计量。"""
    counts: Dict[str, float] = {}
    item_count = 0

    while index < len(tokens):
        token = tokens[index]

        if token in _BRACKET_CLOSE:
            child, index = _parse_formula_group(
                tokens,
                index + 1,
                _BRACKET_CLOSE[token],
            )
            multiplier = 1.0
            if index < len(tokens) and tokens[index][0].isdigit():
                multiplier = _positive_multiplier(tokens[index])
                index += 1
            for elem, count in child.items():
                counts[elem] = counts.get(elem, 0.0) + count * multiplier
            item_count += 1
            continue

        if token in _BRACKET_OPEN:
            if expected_close is None:
                raise ValueError(f"括号不匹配: 多余的 '{token}'")
            if token != expected_close:
                raise ValueError(
                    f"括号不匹配: 期望 '{expected_close}' 但收到 '{token}'"
                )
            if item_count == 0:
                raise ValueError("括号内不能为空")
            return counts, index + 1

        if token[0].isdigit():
            raise ValueError(f"计量数位置非法: {token}")

        elem = token
        index += 1
        multiplier = 1.0
        if index < len(tokens) and tokens[index][0].isdigit():
            multiplier = _positive_multiplier(tokens[index])
            index += 1
        counts[elem] = counts.get(elem, 0.0) + multiplier
        item_count += 1

    if expected_close is not None:
        raise ValueError(f"括号不匹配: 缺少 '{expected_close}'")
    if item_count == 0:
        raise ValueError("化学式为空")
    return counts, index


def calc_molar_mass_from_elements(elements: Dict[str, float]) -> float:
    """根据元素组成计算摩尔质量"""
    return sum(count * ELEMENT_ATOMIC_WEIGHTS[elem] for elem, count in elements.items())


# ── A002 化学式解析 ──

class A002_ChemicalFormulaParser(BaseModelTool):
    model_id = "A002"
    name = "化学式解析"
    scenario = "通用数据与校验"
    priority = "P0"
    version = "1.0.0"
    applicable_boundary = "支持含括号的化学式；不支持同位素标记"

    input_fields = [
        InputField("formula", "化学式", type="string", required=True,
                    placeholder="如 Fe2(SO4)3, CaCO3, Mg(OH)2"),
    ]

    output_fields = [
        OutputField("elements", "元素组成", type="object"),
        OutputField("molar_mass", "摩尔质量 (g/mol)", type="number"),
        OutputField("formula_display", "显示格式", type="string"),
    ]

    def invoke(self, params: dict, context: Optional[InvocationContext] = None) -> ModelResult:
        formula = params["formula"]
        elements, error = parse_formula(formula)
        if error:
            return ModelResult(success=False, error=error, error_code="PARSE_ERROR")

        mm = calc_molar_mass_from_elements(elements)

        total_atoms = sum(elements.values())
        mass_fractions = {}
        for elem, count in elements.items():
            elem_mass = count * ELEMENT_ATOMIC_WEIGHTS[elem]
            mass_fractions[elem] = round(elem_mass / mm, 6)

        return ModelResult(
            success=True,
            result={
                "elements": {k: (v if v == int(v) else v) for k, v in elements.items()},
                "element_count": len(elements),
                "total_atoms": total_atoms,
                "molar_mass": round(mm, 4),
                "mass_fractions": mass_fractions,
                "formula_display": formula,
                "is_stoichiometric": all(v == int(v) for v in elements.values()),
            },
        )


# ── A003 摩尔质量计算 ──

class A003_MolarMassCalculator(BaseModelTool):
    model_id = "A003"
    name = "摩尔质量计算"
    scenario = "通用数据与校验"
    priority = "P0"
    version = "1.0.0"
    applicable_boundary = "基于 IUPAC 2021 原子量"

    input_fields = [
        InputField("formula", "化学式", type="string", required=True,
                    placeholder="如 Fe2O3, H2SO4, CaCO3"),
    ]

    output_fields = [
        OutputField("molar_mass", "摩尔质量 (g/mol)", type="number"),
        OutputField("formula", "化学式", type="string"),
    ]

    def invoke(self, params: dict, context: Optional[InvocationContext] = None) -> ModelResult:
        formula = params["formula"]
        elements, error = parse_formula(formula)
        if error:
            return ModelResult(success=False, error=error, error_code="PARSE_ERROR")

        mm = calc_molar_mass_from_elements(elements)
        return ModelResult(
            success=True,
            result={
                "molar_mass": round(mm, 4),
                "formula": formula,
                "unit": "g/mol",
            },
        )


# ── A004 成分归一化 ──

class A004_CompositionNormalizer(BaseModelTool):
    model_id = "A004"
    name = "成分归一化"
    scenario = "通用数据与校验"
    priority = "P0"
    version = "1.0.0"
    applicable_boundary = "输入各组分分数（质量或摩尔），总和可不等于1"

    input_fields = [
        InputField("compositions", "组成", type="object", required=True,
                    description='如 {"Fe": 0.94, "C": 0.005, "Si": 0.003}'),
        InputField("tolerance", "容差", type="number", required=False, default=0.001,
                    min_value=0.0,
                    description="归一化偏差容差"),
    ]

    output_fields = [
        OutputField("normalized", "归一化组成", type="object"),
        OutputField("sum_before", "归一化前总和", type="number"),
        OutputField("deviation", "偏差", type="number"),
        OutputField("passed", "是否通过", type="boolean"),
    ]

    def validate_input(self, params: dict) -> List[str]:
        errors = super().validate_input(params)
        if errors:
            return errors

        comps = params.get("compositions")
        if not isinstance(comps, dict):
            return ["compositions 必须是组分名称到数值的对象"]
        if not comps:
            return ["compositions 不能为空"]

        values = []
        for name, raw_value in comps.items():
            if isinstance(raw_value, bool):
                errors.append(f"compositions.{name} 必须是数值")
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                errors.append(f"compositions.{name} 必须是数值")
                continue
            if not math.isfinite(value):
                errors.append(f"compositions.{name} 必须是有限数值")
            elif value < 0:
                errors.append(f"compositions.{name} 不能为负数")
            values.append(value)

        if not errors:
            total = sum(values)
            if not math.isfinite(total):
                errors.append("compositions 总和必须是有限数值")
            elif total <= 0:
                errors.append("compositions 总和必须大于0")
        return errors

    def invoke(self, params: dict, context: Optional[InvocationContext] = None) -> ModelResult:
        comps = params.get("compositions", {})
        tol = float(params.get("tolerance", 0.001))

        if not comps:
            return ModelResult(success=False, error="组成不能为空", error_code="INVALID_INPUT")

        values = [float(v) for v in comps.values()]
        if any(not math.isfinite(value) for value in values):
            return ModelResult(
                success=False,
                error="组成必须为有限数值",
                error_code="INVALID_INPUT",
            )
        if any(value < 0 for value in values):
            return ModelResult(
                success=False,
                error="组成不能为负数",
                error_code="INVALID_INPUT",
            )
        if not math.isfinite(tol) or tol < 0:
            return ModelResult(
                success=False,
                error="容差必须为有限非负数",
                error_code="INVALID_INPUT",
            )
        total = sum(values)

        if total == 0:
            return ModelResult(success=False, error="组成总和为0", error_code="INVALID_INPUT")

        normalized = {k: round(float(v) / total, 6) for k, v in comps.items()}
        deviation = abs(total - 1.0)
        passed = deviation <= tol

        warnings = []
        if not passed:
            warnings.append(BoundaryWarning(
                field="compositions", level="warning",
                message=f"归一化前总和 {total:.6f}，偏差 {deviation:.6f} 超出容差 {tol}",
            ))

        return ModelResult(
            success=True,
            result={
                "normalized": normalized,
                "sum_before": round(total, 6),
                "sum_after": 1.0,
                "deviation": round(deviation, 6),
                "passed": passed,
            },
            boundary_check=BoundaryCheck(passed=passed, warnings=warnings),
        )


# ── A005 元素质量守恒校验 ──

class A005_MassBalanceChecker(BaseModelTool):
    model_id = "A005"
    name = "元素质量守恒校验"
    scenario = "通用数据与校验"
    priority = "P0"
    version = "1.0.0"
    applicable_boundary = "输入输出物料流中各元素质量分数"

    input_fields = [
        InputField("input_streams", "输入物流", type="object", required=True,
                    description='[{"name":"铁水","mass":100,"elements":{"Fe":0.94,"C":0.04}}, ...]'),
        InputField("output_streams", "输出物流", type="object", required=True,
                    description='[{"name":"钢水","mass":92,"elements":{"Fe":0.98,"C":0.001}}, ...]'),
        InputField("tolerance", "容差", type="number", required=False, default=0.001),
    ]

    output_fields = [
        OutputField("element_balances", "元素平衡", type="object"),
        OutputField("closure_rate", "闭合率", type="number"),
        OutputField("passed", "是否通过", type="boolean"),
    ]

    def invoke(self, params: dict, context: Optional[InvocationContext] = None) -> ModelResult:
        inputs = params.get("input_streams", [])
        outputs = params.get("output_streams", [])
        tol = float(params.get("tolerance", 0.001))

        if not inputs or not outputs:
            return ModelResult(success=False, error="输入和输出物流不能为空", error_code="INVALID_INPUT")

        # 计算各元素总输入和总输出质量
        input_masses: Dict[str, float] = {}
        output_masses: Dict[str, float] = {}

        total_in_mass = 0
        for stream in inputs:
            mass = float(stream.get("mass", 0))
            total_in_mass += mass
            for elem, frac in stream.get("elements", {}).items():
                input_masses[elem] = input_masses.get(elem, 0) + mass * float(frac)

        total_out_mass = 0
        for stream in outputs:
            mass = float(stream.get("mass", 0))
            total_out_mass += mass
            for elem, frac in stream.get("elements", {}).items():
                output_masses[elem] = output_masses.get(elem, 0) + mass * float(frac)

        # 逐个元素计算残差
        all_elements = set(input_masses.keys()) | set(output_masses.keys())
        balances = {}
        max_residual = 0
        for elem in sorted(all_elements):
            inp = input_masses.get(elem, 0)
            out = output_masses.get(elem, 0)
            residual = inp - out
            max_residual = max(max_residual, abs(residual))
            balances[elem] = {
                "input": round(inp, 4),
                "output": round(out, 4),
                "residual": round(residual, 4),
                "closure": round(1 - abs(residual) / (inp if inp else 1), 6),
            }

        mass_closure = 1 - abs(total_in_mass - total_out_mass) / (total_in_mass if total_in_mass else 1)
        passed = max_residual <= tol

        return ModelResult(
            success=True,
            result={
                "element_balances": balances,
                "total_input_mass": round(total_in_mass, 4),
                "total_output_mass": round(total_out_mass, 4),
                "mass_closure_rate": round(mass_closure, 6),
                "max_element_residual": round(max_residual, 6),
                "passed": passed,
            },
            boundary_check=BoundaryCheck(
                passed=passed,
                warnings=[] if passed else [
                    BoundaryWarning(field="mass_balance", level="warning",
                                    message=f"最大元素残差 {max_residual:.6f} 超出容差 {tol}")
                ],
            ),
        )
