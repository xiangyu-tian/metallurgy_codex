"""Prepare the AI-assisted CF-05B review packet for the 17 implemented tools.

This script is diagnostic only. It does not update CF-05 acceptance state and
does not modify any model implementation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

from models_core import ModelRegistry  # noqa: E402
from models_core.chemical_data import find_reaction  # noqa: E402
import models_core.models_b as models_b  # noqa: E402
from models_core.repositories.thermodynamic_repository import repo  # noqa: E402


PRIMARY_REFERENCES = {
    "nist_shomate": "https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185&Mask=35",
    "nasa_polynomial": "https://ntrs.nasa.gov/citations/20020085330",
    "ciaaw_atomic_weights": "https://www.ciaaw.org/atomic-weights.htm",
    "iupac_equilibrium": "https://goldbook.iupac.org/terms/view/S05915",
    "iupac_gibbs": "https://goldbook.iupac.org/terms/view/G02629",
    "iupac_arrhenius": "https://goldbook.iupac.org/terms/view/A00446",
    "nist_constants": "https://www.physics.nist.gov/cgi-bin/cuu/Info/Constants/ArchiveASCII/allascii_2010.txt",
}


AI_FINDINGS = {
    "A001": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "high",
        "scientific_scope": "线性单位换算和有限的温标偏移换算。",
        "key_risk": "委托路径使用strict=False，实测1 kg→m仍返回success和数值1.0；维度错误没有成为调用失败。",
        "required_action": "跨量纲必须返回失败；冻结支持单位表和温标边界，并明确仿射温标不能只用conversion_factor表达。",
        "reference_keys": [],
    },
    "A002": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "high",
        "scientific_scope": "普通化学式、括号与化学计量数解析。",
        "key_risk": "解析器没有验证输入字符串被完整消费，尾随非法字符可被静默忽略。",
        "required_action": "改为完整词法解析；遇到任何未消费字符、非法小数或水合物/电荷等未支持语法必须显式拒绝。",
        "reference_keys": [],
    },
    "A003": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "high",
        "scientific_scope": "基于标准原子量的化学式摩尔质量计算。",
        "key_risk": "依赖A002解析器，非法尾随字符会被忽略；原子量版本需要可追溯冻结。",
        "required_action": "先修复A002完整解析，再冻结CIAAW/IUPAC原子量版本、例外元素和不确定度说明。",
        "reference_keys": ["ciaaw_atomic_weights"],
    },
    "A004": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "high",
        "scientific_scope": "质量分数或摩尔分数的归一化。",
        "key_risk": "当前允许负组分和非有限值，且未显式记录质量/摩尔基准。",
        "required_action": "拒绝负数、NaN和无穷值；增加composition_basis并规定容差语义。",
        "reference_keys": [],
    },
    "A005": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "high",
        "scientific_scope": "按物料流计算元素输入、输出和守恒残差。",
        "key_risk": "当前允许负质量/负分数；tolerance按绝对质量残差比较但未声明单位，输出Schema与实际closure字段也需对齐。",
        "required_action": "校验质量和分数非负、分数基准与总和；把绝对/相对容差分开，并对齐输出契约。",
        "reference_keys": [],
    },
    "B001": {
        "ai_disposition": "candidate_after_minor_clarification",
        "risk_level": "medium",
        "scientific_scope": "在给定物种、相态和有效温区内计算Shomate Cp、H°−H°298.15和S°。",
        "key_risk": "必须严格绑定相态、系数来源和温区；H字段是焓增量，不是绝对焓。",
        "required_action": "在Schema和结果中固定相态、有效温区、系数版本及H_minus_H298语义。",
        "reference_keys": ["nist_shomate"],
    },
    "B002": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "high",
        "scientific_scope": "名义上是NASA多项式热物性计算。",
        "key_risk": "当前实际调用Shomate并明确标注“NASA近似”，不构成独立NASA多项式实现。",
        "required_action": "实现真正NASA 7/9项系数和温区，或与B001合并并更名，不能按独立NASA工具接受。",
        "reference_keys": ["nasa_polynomial", "nist_shomate"],
    },
    "B003": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "critical",
        "scientific_scope": "由Shomate焓函数计算两温度间显热。",
        "key_risk": "结果为摩尔焓差，却直接乘以mass(g)，存在量纲错误；同时不含相变潜热。",
        "required_action": "输入改为amount_mol，或使用摩尔质量把质量换算为物质的量；跨相变时拒绝或加入潜热。",
        "reference_keys": ["nist_shomate"],
    },
    "B004": {
        "ai_disposition": "candidate_after_minor_clarification",
        "risk_level": "medium",
        "scientific_scope": "同一相态和有效温区内的S(T2)−S(T1)。",
        "key_risk": "跨相变不包含相变熵；名称写“数值积分”，实现实际上使用Shomate解析熵差。",
        "required_action": "限制同相态有效温区，并把方法描述改为解析熵差或加入分段积分。",
        "reference_keys": ["nist_shomate"],
    },
    "B005": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "critical",
        "scientific_scope": "由焓和熵构造单物种Gibbs能。",
        "key_risk": "当前用H°−H°298.15与绝对S°直接计算G，参考态不一致，结果不是完整标准摩尔Gibbs能。",
        "required_action": "加入标准生成焓/一致参考态，或把工具明确改名为热Gibbs函数增量。",
        "reference_keys": ["nist_shomate", "iupac_gibbs"],
    },
    "B006": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "high",
        "scientific_scope": "由各物种热化学数据计算反应焓。",
        "key_risk": "内置兜底对任意温度返回同一298.15 K反应焓；数据库路径也未完整加入各物种显热修正。",
        "required_action": "明确仅支持298.15 K，或使用一致的Cp/焓函数计算ΔrH(T)。",
        "reference_keys": ["nist_shomate"],
    },
    "B007": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "high",
        "scientific_scope": "由各物种标准熵计算反应熵。",
        "key_risk": "内置兜底对任意温度返回同一ΔS；数据库与兜底的温度语义不一致。",
        "required_action": "明确298.15 K限定，或逐物种计算S°(T)并统一数据库/兜底行为。",
        "reference_keys": ["nist_shomate"],
    },
    "B008": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "critical",
        "scientific_scope": "由ΔH和ΔS估算标准反应Gibbs能。",
        "key_risk": "继承B006/B007温度问题；pressure输入完全未参与计算，却输出反应方向判断。",
        "required_action": "删除无效pressure参数或引入活度/分压项；使用一致的ΔrG°(T)，区分标准态与实际反应商。",
        "reference_keys": ["iupac_gibbs", "iupac_equilibrium"],
    },
    "B009": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "critical",
        "scientific_scope": "由标准反应Gibbs能计算热力学平衡常数。",
        "key_risk": "公式本身正确，但上游ΔG°温度处理不完整；T≤0没有前置校验，指数可能溢出。",
        "required_action": "先修复ΔrG°(T)，再增加T>0、指数稳定计算和无量纲标准态说明。",
        "reference_keys": ["iupac_equilibrium"],
    },
    "B019": {
        "ai_disposition": "candidate_after_minor_clarification",
        "risk_level": "low",
        "scientific_scope": "二元系两相区的杠杆规则相分数计算。",
        "key_risk": "需要明确质量/摩尔分数基准，并禁止把结果外推到多元系或多相区。",
        "required_action": "增加composition_basis枚举并保留总体成分必须位于两端点之间的校验。",
        "reference_keys": [],
    },
    "C001": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "high",
        "scientific_scope": "经典Arrhenius速率常数。",
        "key_risk": "未校验A>0、R>0和参数有限性；负A可返回success及-ln无穷值。",
        "required_action": "增加A>0、R>0、T>0、有限值检查，并明确A的单位随反应级数变化。",
        "reference_keys": ["iupac_arrhenius"],
    },
    "C002": {
        "ai_disposition": "revision_required_before_acceptance",
        "risk_level": "critical",
        "scientific_scope": "Arrhenius型扩散系数。",
        "key_risk": "eV分支把单粒子eV转成J后仍除以摩尔气体常数R，量纲错误；应使用kB或转成J/mol。",
        "required_action": "eV输入乘以Faraday常数转为J/mol，或改用Boltzmann常数；同时校验D0>0与T>0。",
        "reference_keys": ["nist_constants", "iupac_arrhenius"],
    },
}


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def result_dict(result):
    return json_safe({
        "success": result.success,
        "error": result.error,
        "error_code": result.error_code,
        "result": result.result,
        "boundary_check": (
            {
                "passed": result.boundary_check.passed,
                "warnings": [
                    {
                        "field": warning.field,
                        "message": warning.message,
                        "level": warning.level,
                    }
                    for warning in result.boundary_check.warnings
                ],
            }
            if result.boundary_check
            else None
        ),
    })


def run_diagnostics(registry: ModelRegistry):
    diagnostics = {}

    def invoke(model_id, params):
        return result_dict(registry.invoke(model_id, deepcopy(params)))

    diagnostics["A001"] = {
        "diagnostic": "跨量纲换算应拒绝",
        "observed": invoke("A001", {"value": 1, "source_unit": "kg", "target_unit": "m"}),
        "finding": "defect_if_success",
    }
    diagnostics["A002"] = {
        "diagnostic": "尾随非法字符应拒绝",
        "observed": invoke("A002", {"formula": "Fe2O3abc"}),
        "finding": "defect_if_success",
    }
    diagnostics["A003"] = {
        "diagnostic": "摩尔质量计算不应忽略非法尾随字符",
        "observed": invoke("A003", {"formula": "Fe2O3abc"}),
        "finding": "defect_if_success",
    }
    diagnostics["A004"] = {
        "diagnostic": "负组分应拒绝",
        "observed": invoke("A004", {"compositions": {"Fe": 1.1, "C": -0.1}}),
        "finding": "defect_if_success",
    }
    diagnostics["A005"] = {
        "diagnostic": "负质量物流应拒绝",
        "observed": invoke(
            "A005",
            {
                "input_streams": [{"name": "in", "mass": -100, "elements": {"Fe": 1.0}}],
                "output_streams": [{"name": "out", "mass": -100, "elements": {"Fe": 1.0}}],
            },
        ),
        "finding": "defect_if_success",
    }
    diagnostics["B001"] = {
        "diagnostic": "超出Shomate有效温区应拒绝",
        "observed": invoke("B001", {"species": "Fe(s)", "temperature": 100}),
        "finding": "pass_if_rejected",
    }
    b002 = invoke("B002", {"species": "Fe(s)", "temperature": 1000})
    diagnostics["B002"] = {
        "diagnostic": "NASA工具是否实际使用NASA系数",
        "observed": b002,
        "finding": "defect_if_method_contains_shomate",
    }
    b003_1 = invoke(
        "B003",
        {"species": "Fe(s)", "temperature_start": 400, "temperature_end": 1000, "mass": 1},
    )
    b003_2 = invoke(
        "B003",
        {"species": "Fe(s)", "temperature_start": 400, "temperature_end": 1000, "mass": 2},
    )
    diagnostics["B003"] = {
        "diagnostic": "mass(g)缩放是否具有物质的量换算",
        "observed": {
            "mass_1g": b003_1,
            "mass_2g": b003_2,
            "ratio": (
                b003_2["result"]["delta_H"] / b003_1["result"]["delta_H"]
                if b003_1["success"] and b003_2["success"] and b003_1["result"]["delta_H"]
                else None
            ),
        },
        "finding": "dimension_defect_if_ratio_is_2_without_molar_mass",
    }
    diagnostics["B004"] = {
        "diagnostic": "起始温度不小于终止温度应拒绝",
        "observed": invoke(
            "B004",
            {"species": "Fe(s)", "temperature_start": 1000, "temperature_end": 400},
        ),
        "finding": "pass_if_rejected",
    }
    diagnostics["B005"] = {
        "diagnostic": "结果是否包含一致的标准参考焓",
        "observed": invoke("B005", {"species": "Fe(s)", "temperature": 298.15}),
        "finding": "reference_state_review_required",
    }
    b006_298 = invoke("B006", {"reaction": "C + O₂ → CO₂", "temperature": 298.15})
    b006_1200 = invoke("B006", {"reaction": "C + O₂ → CO₂", "temperature": 1200})
    diagnostics["B006"] = {
        "diagnostic": "内置兜底ΔH是否随温度修正",
        "observed": {"T298": b006_298, "T1200": b006_1200},
        "finding": "defect_if_delta_H_identical",
    }
    b007_298 = invoke("B007", {"reaction": "C + O₂ → CO₂", "temperature": 298.15})
    b007_1200 = invoke("B007", {"reaction": "C + O₂ → CO₂", "temperature": 1200})
    diagnostics["B007"] = {
        "diagnostic": "内置兜底ΔS是否随温度修正",
        "observed": {"T298": b007_298, "T1200": b007_1200},
        "finding": "defect_if_delta_S_identical",
    }
    b008_low_p = invoke(
        "B008",
        {"reaction": "C + O₂ → CO₂", "temperature": 1000, "pressure": 101325},
    )
    b008_high_p = invoke(
        "B008",
        {"reaction": "C + O₂ → CO₂", "temperature": 1000, "pressure": 10_000_000},
    )
    diagnostics["B008"] = {
        "diagnostic": "pressure输入是否实际参与计算",
        "observed": {"low_pressure": b008_low_p, "high_pressure": b008_high_p},
        "finding": "defect_if_outputs_identical",
    }
    diagnostics["B009"] = {
        "diagnostic": "T=0应由前置边界校验拒绝",
        "observed": invoke("B009", {"reaction": "C + O₂ → CO₂", "temperature": 0}),
        "finding": "defect_if_internal_error",
    }
    diagnostics["B019"] = {
        "diagnostic": "总体成分超出两相端点应拒绝",
        "observed": invoke(
            "B019",
            {
                "overall_composition": 0.9,
                "phase1_composition": 0.1,
                "phase2_composition": 0.8,
            },
        ),
        "finding": "pass_if_rejected",
    }
    diagnostics["C001"] = {
        "diagnostic": "负指前因子A应拒绝",
        "observed": invoke(
            "C001",
            {"A": -1.0, "Ea": 50_000, "temperature": 1000, "Ea_unit": "J/mol"},
        ),
        "finding": "defect_if_success",
    }
    c002 = invoke(
        "C002",
        {"D0": 1.0, "Q": 1.0, "temperature": 1000, "Q_unit": "eV"},
    )
    expected_ratio = math.exp(-96_485.33212 / (8.314462618 * 1000))
    diagnostics["C002"] = {
        "diagnostic": "1 eV激活能是否按每摩尔能量处理",
        "observed": c002,
        "expected_D_over_D0_approximately": expected_ratio,
        "finding": "defect_if_observed_near_1",
    }
    return diagnostics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    registry = ModelRegistry()
    registry.discover()
    cards = sorted(registry.list_models(), key=lambda card: card["model_code"])
    if len(cards) != 17:
        raise SystemExit(f"expected 17 models, got {len(cards)}")

    golden_path = TOOLS_DIR / "benchmarks" / "golden_cases.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    golden_counts = Counter(case["model_code"] for case in golden["cases"])

    cf05a_path = WORKSPACE / "outputs" / "cf05a_tool_inventory_20260730" / "cf05a_tool_inventory_precheck.json"
    cf05a = json.loads(cf05a_path.read_text(encoding="utf-8"))
    source_by_id = {tool["model_id"]: tool for tool in cf05a["tools"]}

    with ExitStack() as stack:
        stack.enter_context(patch.object(repo, "find_correlation", return_value=None))
        stack.enter_context(patch.object(repo, "get_property", return_value=None))
        stack.enter_context(
            patch.object(
                models_b,
                "_lookup_reaction",
                side_effect=lambda reaction, temperature=298.15: find_reaction(reaction),
            )
        )
        diagnostics = run_diagnostics(registry)

    review_rows = []
    naming_map = []
    for card in cards:
        model_id = card["model_code"]
        source = source_by_id[model_id]
        finding = AI_FINDINGS[model_id]
        required_fields = list(card["input_schema"].get("required", []))
        review_rows.append(
            {
                "model_id": model_id,
                "model_name": card["model_name"],
                "category": card["category"],
                "version": card["version"],
                "description": card["description"],
                "applicable_conditions": card["applicable_conditions"],
                "input_schema": card["input_schema"],
                "output_schema": card["output_schema"],
                "input_units": card["input_units"],
                "output_units": card["output_units"],
                "formula_reference": card["formula_reference"],
                "required_data": card["required_data"],
                "data_source": card["data_source"],
                "dependencies": card["dependencies"],
                "source_file": source["registry_source_file"],
                "golden_case_count": golden_counts[model_id],
                "required_field_count": len(required_fields),
                "generated_invalid_input_case_count": len(required_fields) * 5,
                "diagnostic": diagnostics[model_id],
                **finding,
                "reference_urls": [
                    PRIMARY_REFERENCES[key] for key in finding["reference_keys"]
                ],
                "human_decision": None,
                "human_reviewer": None,
                "reviewed_at": None,
                "human_note": None,
            }
        )
        naming_map.append(
            {
                "model_id": model_id,
                "canonical_tool_id": model_id,
                "planned_semantic_alias": source["api_name"],
                "registry_api_name": source["registry_api_name"],
                "runtime_openai_tool_name": source["runtime_openai_tool_name"],
                "recommended_policy": (
                    "保留model_id为稳定主键和当前LLM函数名；"
                    "保留规划API函数名为semantic_alias；"
                    "日志同时记录三者，不在本阶段破坏性重命名。"
                ),
                "mapping_status": "proposed_not_frozen",
                "human_decision": None,
                "human_reviewer": None,
                "reviewed_at": None,
                "human_note": None,
            }
        )

    disposition_counts = Counter(row["ai_disposition"] for row in review_rows)
    risk_counts = Counter(row["risk_level"] for row in review_rows)
    document = {
        "schema_version": "1.0",
        "audit_id": "CF05B-17-TOOL-REVIEW-20260730",
        "status": "ai_pre_review_complete_human_confirmation_pending",
        "formal_cf05_accepted_count": 0,
        "summary": {
            "tool_count": len(review_rows),
            "disposition_counts": dict(disposition_counts),
            "risk_counts": dict(risk_counts),
            "human_confirmed_count": 0,
            "naming_mapping_status": "proposed_not_frozen",
        },
        "primary_references": PRIMARY_REFERENCES,
        "tools": review_rows,
        "naming_map": naming_map,
        "governance_note": (
            "AI预审用于缩小人工复核范围；不得自动写入CF-05 accepted。"
            "人工至少需要确认所有revision_required_before_acceptance项和命名映射政策。"
        ),
    }
    output_path = output_dir / "cf05b_17_tool_ai_review.json"
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(document["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
